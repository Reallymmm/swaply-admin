from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal, get_db
from .models import User, Category, Listing, Review
from .mobile import router as mobile_router, UPLOADS_DIR, photo_out, avatar_url, rating_stats

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

STATUSES = ["active", "review", "blocked"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(100)"))
    yield


app = FastAPI(title="Swaply", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ручки для мобильного приложения
app.include_router(mobile_router)

# загруженные фотографии объявлений доступны по адресу /uploads/<имя файла>
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")



class StatusIn(BaseModel):
    status: str


class CategoryIn(BaseModel):
    name: str


class UserEditIn(BaseModel):
    name: str


def listing_dict(x: Listing):
    return {
        "id": x.id,
        "title": x.title,
        "description": x.description,
        "want": x.want,
        "city": x.city,
        "status": x.status,
        "category": x.category.name if x.category else None,
        "author": x.owner.name,
        "author_id": x.owner_id,
        "photos": [photo_out(p) for p in x.photos],
        "cover": f"/uploads/{x.photos[0].filename}" if x.photos else None,
        "created_at": x.created_at.isoformat(),
    }


def user_dict(u: User):
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "city": u.city,
        "is_blocked": u.is_blocked,
        "avatar": avatar_url(u),
        "listings_count": len(u.listings),
        "created_at": u.created_at.isoformat(),
    }


@app.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where))

    return {
        "users": count(User),
        "active": count(Listing, Listing.status == "active"),
        "review": count(Listing, Listing.status == "review"),
        "blocked": count(Listing, Listing.status == "blocked"),
    }



@app.get("/api/listings")
def api_listings(status: str | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    query = select(Listing).order_by(Listing.created_at.desc(), Listing.id.desc())
    if status:
        query = query.where(Listing.status == status)
    if limit:
        query = query.limit(limit)
    return [listing_dict(x) for x in db.scalars(query).all()]


@app.get("/api/listings/{listing_id}")
def api_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Объявление не найдено")
    return listing_dict(listing)


@app.post("/api/listings/{listing_id}/status")
def api_set_status(listing_id: int, data: StatusIn, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Объявление не найдено")
    if data.status not in STATUSES:
        raise HTTPException(400, "Неизвестный статус")
    listing.status = data.status
    db.commit()
    return listing_dict(listing)


# ---------- пользователи ----------

@app.get("/api/users")
def api_users(db: Session = Depends(get_db)):
    return [user_dict(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@app.get("/api/users/{user_id}")
def api_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    out = user_dict(user)
    out["listings"] = [
        listing_dict(x) for x in sorted(user.listings, key=lambda l: (l.created_at, l.id), reverse=True)
    ]
    reviews = db.scalars(
        select(Review).where(Review.seller_id == user.id).order_by(Review.created_at.desc(), Review.id.desc())
    ).all()
    out["rating"], out["reviews_count"] = rating_stats(db, user.id)
    out["reviews"] = [
        {"id": r.id, "author": r.author.name, "rating": r.rating, "text": r.text,
         "created_at": r.created_at.isoformat()}
        for r in reviews
    ]
    return out


@app.put("/api/users/{user_id}")
def api_edit_user(user_id: int, data: UserEditIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    name = " ".join(data.name.split())
    if not name:
        raise HTTPException(400, "Введите ФИО")
    if len(name) > 100:
        raise HTTPException(400, "ФИО слишком длинное (до 100 символов)")
    user.name = name
    db.commit()
    return user_dict(user)


@app.delete("/api/users/{user_id}/avatar")
def api_delete_avatar(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    old = user.avatar
    user.avatar = None
    db.commit()
    if old:
        (UPLOADS_DIR / old).unlink(missing_ok=True)
    return user_dict(user)


@app.post("/api/users/{user_id}/toggle-block")
def api_toggle_block(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.is_blocked = not user.is_blocked
    db.commit()
    return user_dict(user)



@app.get("/api/categories")
def api_categories(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Category, func.count(Listing.id))
        .outerjoin(Listing, Listing.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.id)
    ).all()
    return [{"id": c.id, "name": c.name, "listings_count": n} for c, n in rows]


@app.post("/api/categories")
def api_add_category(data: CategoryIn, db: Session = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Пустое название")
    if db.scalar(select(Category).where(Category.name == name)):
        raise HTTPException(409, "Такая категория уже есть")
    category = Category(name=name)
    db.add(category)
    db.commit()
    return {"id": category.id, "name": category.name, "listings_count": 0}


@app.delete("/api/categories/{category_id}")
def api_delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Категория не найдена")
    db.delete(category)  # у её объявлений category_id станет пустым
    db.commit()
    return {"ok": True}

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
