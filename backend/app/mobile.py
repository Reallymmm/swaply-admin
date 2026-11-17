import base64
import binascii
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, Category, Listing, ListingPhoto, Review, Favorite, Chat, Message
from .security import hash_password, verify_password, new_token

router = APIRouter(prefix="/api/m")

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 12 * 1024 * 1024



class RegisterIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class ListingIn(BaseModel):
    title: str
    description: str = ""
    want: str = ""
    category_id: int | None = None


class PhotoIn(BaseModel):
    data: str

class ReviewIn(BaseModel):
    rating: int
    text: str = ""


class ChatIn(BaseModel):
    listing_id: int


class MessageIn(BaseModel):
    text: str



def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    """Достаёт пользователя по токену из заголовка Authorization: Bearer <токен>."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Нужно войти в аккаунт")
    user = db.scalar(select(User).where(User.token == authorization[7:]))
    if not user:
        raise HTTPException(401, "Нужно войти в аккаунт")
    if user.is_blocked:
        raise HTTPException(403, "Аккаунт заблокирован администратором")
    return user



def avatar_url(u: User) -> str | None:
    return f"/uploads/{u.avatar}" if u.avatar else None


def rating_stats(db: Session, user_id: int):
    avg, count = db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(Review.seller_id == user_id)
    ).one()
    return (round(float(avg), 1) if avg is not None else None), count


def user_out(u: User):
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "city": u.city,
        "avatar": avatar_url(u),
        "created_at": u.created_at.isoformat(),
    }


def public_user_out(u: User):
    return {
        "id": u.id,
        "name": u.name,
        "city": u.city,
        "avatar": avatar_url(u),
        "created_at": u.created_at.isoformat(),
    }


def review_out(r: Review, viewer: User):
    return {
        "id": r.id,
        "author": r.author.name,
        "author_avatar": avatar_url(r.author),
        "rating": r.rating,
        "text": r.text,
        "created_at": r.created_at.isoformat(),
        "mine": r.author_id == viewer.id,
    }


def photo_out(p: ListingPhoto):
    return {"id": p.id, "url": f"/uploads/{p.filename}"}


def favorite_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(Favorite.listing_id).where(Favorite.user_id == user.id)).all())


def listing_out(x: Listing, favs: set[int], user: User):
    return {
        "id": x.id,
        "title": x.title,
        "description": x.description,
        "want": x.want,
        "city": x.city,
        "status": x.status,
        "category": x.category.name if x.category else None,
        "category_id": x.category_id,
        "author": x.owner.name,
        "author_id": x.owner_id,
        "author_avatar": avatar_url(x.owner),
        "photos": [photo_out(p) for p in x.photos],
        "cover": f"/uploads/{x.photos[0].filename}" if x.photos else None,
        "created_at": x.created_at.isoformat(),
        "is_favorite": x.id in favs,
        "is_mine": x.owner_id == user.id,
    }


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    name = data.name.strip()
    email = data.email.strip().lower()
    if not name:
        raise HTTPException(400, "Введите имя")
    if "@" not in email:
        raise HTTPException(400, "Введите корректный email")
    if len(data.password) < 6:
        raise HTTPException(400, "Пароль должен быть не короче 6 символов")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Пользователь с таким email уже есть")

    user = User(name=name, email=email, city="", password_hash=hash_password(data.password), token=new_token())
    db.add(user)
    db.commit()
    return {"token": user.token, "user": user_out(user)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    if user.is_blocked:
        raise HTTPException(403, "Аккаунт заблокирован администратором")
    if not user.token:
        user.token = new_token()
        db.commit()
    return {"token": user.token, "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/me/avatar")
def set_avatar(data: PhotoIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    filename = store_image(data.data)
    old = user.avatar
    user.avatar = filename
    db.commit()
    if old:
        (UPLOADS_DIR / old).unlink(missing_ok=True)
    return user_out(user)


@router.delete("/me/avatar")
def delete_avatar(db: Session = Depends(get_db), user: User = Depends(current_user)):
    old = user.avatar
    user.avatar = None
    db.commit()
    if old:
        (UPLOADS_DIR / old).unlink(missing_ok=True)
    return user_out(user)


@router.get("/users/{user_id}")
def user_profile(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):

    u = db.get(User, user_id)
    if not u or u.is_blocked:
        raise HTTPException(404, "Пользователь не найден")
    query = (
        select(Listing)
        .where(Listing.owner_id == u.id, Listing.status == "active")
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    favs = favorite_ids(db, user)
    listings = [listing_out(x, favs, user) for x in db.scalars(query).all()]
    out = public_user_out(u)
    out["listings_count"] = len(listings)
    out["listings"] = listings

    reviews = db.scalars(
        select(Review).where(Review.seller_id == u.id).order_by(Review.created_at.desc(), Review.id.desc())
    ).all()
    out["rating"], out["reviews_count"] = rating_stats(db, u.id)
    out["reviews"] = [review_out(r, user) for r in reviews]
    out["can_review"] = u.id != user.id
    mine = next((r for r in reviews if r.author_id == user.id), None)
    out["my_review"] = {"rating": mine.rating, "text": mine.text} if mine else None
    return out


@router.post("/users/{user_id}/reviews")
def add_review(user_id: int, data: ReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user)):

    seller = db.get(User, user_id)
    if not seller or seller.is_blocked:
        raise HTTPException(404, "Пользователь не найден")
    if seller.id == user.id:
        raise HTTPException(400, "Нельзя оставить отзыв самому себе")
    if not 1 <= data.rating <= 5:
        raise HTTPException(400, "Оценка должна быть от 1 до 5")
    text = data.text.strip()[:1000]

    review = db.scalar(select(Review).where(Review.seller_id == seller.id, Review.author_id == user.id))
    if review:
        review.rating = data.rating
        review.text = text
    else:
        db.add(Review(seller_id=seller.id, author_id=user.id, rating=data.rating, text=text))
    db.commit()
    rating, count = rating_stats(db, seller.id)
    return {"rating": rating, "reviews_count": count}


@router.get("/feed")
def feed(q: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Listing).where(Listing.status == "active").order_by(Listing.created_at.desc(), Listing.id.desc())
    q = q.strip()
    if q:
        query = query.where(or_(Listing.title.ilike(f"%{q}%"), Listing.want.ilike(f"%{q}%")))
    favs = favorite_ids(db, user)
    return [listing_out(x, favs, user) for x in db.scalars(query).all()]


@router.get("/listings/{listing_id}")
def listing_detail(listing_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    x = db.get(Listing, listing_id)
    if not x or (x.status != "active" and x.owner_id != user.id):
        raise HTTPException(404, "Объявление не найдено")
    out = listing_out(x, favorite_ids(db, user), user)
    out["author_city"] = x.owner.city
    out["author_rating"], out["author_reviews_count"] = rating_stats(db, x.owner_id)
    out["author_listings"] = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.owner_id == x.owner_id, Listing.status == "active")
    )
    return out


@router.post("/listings")
def create_listing(data: ListingIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    title = data.title.strip()
    if not title:
        raise HTTPException(400, "Введите название")
    x = Listing(
        title=title,
        description=data.description.strip(),
        want=data.want.strip(),
        city=user.city,
        category_id=data.category_id,
        owner_id=user.id,
        status="review",
    )
    db.add(x)
    db.commit()
    return listing_out(x, set(), user)


def own_listing(db: Session, listing_id: int, user: User) -> Listing:
    x = db.get(Listing, listing_id)
    if not x or x.owner_id != user.id:
        raise HTTPException(404, "Объявление не найдено")
    return x


@router.put("/listings/{listing_id}")
def update_listing(listing_id: int, data: ListingIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    x = own_listing(db, listing_id, user)
    title = data.title.strip()
    if not title:
        raise HTTPException(400, "Введите название")
    x.title = title
    x.description = data.description.strip()
    x.want = data.want.strip()
    x.category_id = data.category_id
    db.commit()
    return listing_out(x, favorite_ids(db, user), user)


@router.post("/listings/{listing_id}/toggle-hidden")
def toggle_hidden(listing_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    x = own_listing(db, listing_id, user)
    if x.status == "active":
        x.status = "hidden"
    elif x.status == "hidden":
        x.status = "active"
    else:
        raise HTTPException(400, "Это объявление сейчас нельзя скрыть или показать")
    db.commit()
    return listing_out(x, favorite_ids(db, user), user)


@router.get("/my-listings")
def my_listings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Listing).where(Listing.owner_id == user.id).order_by(Listing.created_at.desc(), Listing.id.desc())
    favs = favorite_ids(db, user)
    return [listing_out(x, favs, user) for x in db.scalars(query).all()]




def detect_extension(raw: bytes) -> str | None:
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return None


def store_image(data_b64: str) -> str:

    try:
        raw = base64.b64decode(data_b64.split(",")[-1])
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Не удалось прочитать фотографию")
    if not raw:
        raise HTTPException(400, "Пустая фотография")
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Фотография слишком большая")
    ext = detect_extension(raw)
    if not ext:
        raise HTTPException(400, "Подходят только JPG, PNG и WEBP")
    filename = f"{uuid.uuid4().hex}.{ext}"
    (UPLOADS_DIR / filename).write_bytes(raw)
    return filename


@router.post("/listings/{listing_id}/photos")
def add_photo(listing_id: int, data: PhotoIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    x = own_listing(db, listing_id, user)
    if len(x.photos) >= MAX_PHOTOS:
        raise HTTPException(400, f"Можно загрузить не больше {MAX_PHOTOS} фото")

    filename = store_image(data.data)
    photo = ListingPhoto(listing_id=x.id, filename=filename)
    db.add(photo)
    db.commit()
    return photo_out(photo)


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    photo = db.get(ListingPhoto, photo_id)
    if not photo or photo.listing.owner_id != user.id:
        raise HTTPException(404, "Фотография не найдена")
    path = UPLOADS_DIR / photo.filename
    db.delete(photo)
    db.commit()
    path.unlink(missing_ok=True)
    return {"ok": True}



@router.get("/favorites")
def favorites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = (
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .where(Favorite.user_id == user.id, Listing.status == "active")
        .order_by(Favorite.id.desc())
    )
    favs = favorite_ids(db, user)
    return [listing_out(x, favs, user) for x in db.scalars(query).all()]


@router.post("/favorites/{listing_id}")
def toggle_favorite(listing_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fav = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.listing_id == listing_id))
    if fav:
        db.delete(fav)
        state = False
    else:
        if not db.get(Listing, listing_id):
            raise HTTPException(404, "Объявление не найдено")
        db.add(Favorite(user_id=user.id, listing_id=listing_id))
        state = True
    db.commit()
    return {"is_favorite": state}



def message_out(m: Message, user: User):
    return {"id": m.id, "text": m.text, "mine": m.sender_id == user.id, "created_at": m.created_at.isoformat()}


def my_chat(db: Session, chat_id: int, user: User) -> Chat:
    c = db.get(Chat, chat_id)
    if not c or user.id not in (c.buyer_id, c.seller_id):
        raise HTTPException(404, "Чат не найден")
    return c


@router.post("/chats")
def open_chat(data: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Открывает чат по объявлению (если его ещё нет - создаёт)."""
    listing = db.get(Listing, data.listing_id)
    if not listing or listing.status != "active":
        raise HTTPException(404, "Объявление не найдено")
    if listing.owner_id == user.id:
        raise HTTPException(400, "Это ваше собственное объявление")
    c = db.scalar(select(Chat).where(Chat.listing_id == listing.id, Chat.buyer_id == user.id))
    if not c:
        c = Chat(listing_id=listing.id, buyer_id=user.id, seller_id=listing.owner_id)
        db.add(c)
        db.commit()
    return {"id": c.id}


@router.get("/chats")
def chats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Chat).where(or_(Chat.buyer_id == user.id, Chat.seller_id == user.id))).all()
    out = []
    for c in rows:
        other = c.seller if c.buyer_id == user.id else c.buyer
        last = c.messages[-1] if c.messages else None
        out.append({
            "id": c.id,
            "other_name": other.name,
            "listing_title": c.listing.title,
            "last_text": last.text if last else "",
            "last_at": (last.created_at if last else c.created_at).isoformat(),
        })
    out.sort(key=lambda row: row["last_at"], reverse=True)
    return out


@router.get("/chats/{chat_id}")
def chat_detail(chat_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = my_chat(db, chat_id, user)
    other = c.seller if c.buyer_id == user.id else c.buyer
    return {
        "id": c.id,
        "other_name": other.name,
        "listing_title": c.listing.title,
        "listing_want": c.listing.want,
        "messages": [message_out(m, user) for m in c.messages],
    }


@router.post("/chats/{chat_id}/messages")
def send_message(chat_id: int, data: MessageIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = my_chat(db, chat_id, user)
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    m = Message(chat_id=c.id, sender_id=user.id, text=text)
    db.add(m)
    db.commit()
    return message_out(m, user)
