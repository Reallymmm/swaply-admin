from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal, get_db
from datetime import datetime

from .models import User, Category, Listing, Review, Appeal, BAN_REASONS
from .mobile import router as mobile_router, UPLOADS_DIR, photo_out, avatar_url, rating_stats, notify

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

STATUSES = ["active", "review", "blocked"]
REVIEW_STATUSES = ["visible", "hidden"]
APPEAL_STATUSES = ["pending", "approved", "rejected"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(100)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason VARCHAR(30)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_comment VARCHAR(300) NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'visible'"))
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


class BlockIn(BaseModel):
    reason: str
    comment: str = ""


class AppealResolveIn(BaseModel):
    decision: str  # approve / reject
    comment: str = ""


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
        "ban_reason": u.ban_reason,
        "ban_reason_name": BAN_REASONS.get(u.ban_reason) if u.ban_reason else None,
        "ban_comment": u.ban_comment,
        "banned_at": u.banned_at.isoformat() if u.banned_at else None,
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
        "appeals": count(Appeal, Appeal.status == "pending"),
        "reviews": count(Review),
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
    changed = listing.status != data.status
    listing.status = data.status
    if changed and data.status == "active":
        notify(db, listing.owner_id, "listing_approved", "Объявление одобрено",
               f"«{listing.title}» прошло модерацию и опубликовано", listing_id=listing.id)
    elif changed and data.status == "blocked":
        notify(db, listing.owner_id, "listing_blocked", "Объявление заблокировано",
               f"«{listing.title}» не прошло модерацию", listing_id=listing.id)
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
        review_dict(r) for r in reviews
    ]
    appeals = db.scalars(select(Appeal).where(Appeal.user_id == user.id).order_by(Appeal.id.desc())).all()
    out["appeals"] = [appeal_dict(a) for a in appeals]
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


@app.get("/api/ban-reasons")
def api_ban_reasons():
    return [{"key": k, "name": v} for k, v in BAN_REASONS.items()]


@app.post("/api/users/{user_id}/block")
def api_block_user(user_id: int, data: BlockIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if data.reason not in BAN_REASONS:
        raise HTTPException(400, "Выберите причину блокировки из списка")
    comment = data.comment.strip()[:300]
    if data.reason == "other" and not comment:
        raise HTTPException(400, "Для причины «Другое» напишите комментарий")
    user.is_blocked = True
    user.ban_reason = data.reason
    user.ban_comment = comment
    user.banned_at = datetime.now()
    db.commit()
    return user_dict(user)


def unblock(db: Session, user: User, comment: str):
    """Снимает блокировку и закрывает висящие апелляции пользователя."""
    user.is_blocked = False
    user.ban_reason = None
    user.ban_comment = ""
    user.banned_at = None
    for a in db.scalars(select(Appeal).where(Appeal.user_id == user.id, Appeal.status == "pending")).all():
        a.status = "approved"
        a.admin_comment = comment
        a.resolved_at = datetime.now()


@app.post("/api/users/{user_id}/unblock")
def api_unblock_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    unblock(db, user, "Аккаунт разблокирован администратором")
    db.commit()
    return user_dict(user)


# ---------- апелляции ----------

def appeal_dict(a: Appeal):
    return {
        "id": a.id,
        "user_id": a.user_id,
        "user": a.user.name,
        "email": a.user.email,
        "is_blocked": a.user.is_blocked,
        "ban_reason": a.ban_reason,
        "ban_reason_name": BAN_REASONS.get(a.ban_reason) if a.ban_reason else None,
        "ban_comment": a.user.ban_comment,
        "text": a.text,
        "status": a.status,
        "admin_comment": a.admin_comment,
        "created_at": a.created_at.isoformat(),
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }


@app.get("/api/appeals")
def api_appeals(status: str | None = None, db: Session = Depends(get_db)):
    query = select(Appeal).order_by(Appeal.created_at.desc(), Appeal.id.desc())
    if status:
        query = query.where(Appeal.status == status)
    return [appeal_dict(a) for a in db.scalars(query).all()]


@app.post("/api/appeals/{appeal_id}/resolve")
def api_resolve_appeal(appeal_id: int, data: AppealResolveIn, db: Session = Depends(get_db)):
    a = db.get(Appeal, appeal_id)
    if not a:
        raise HTTPException(404, "Апелляция не найдена")
    if a.status != "pending":
        raise HTTPException(400, "Эта апелляция уже рассмотрена")
    if data.decision not in ("approve", "reject"):
        raise HTTPException(400, "Неизвестное решение")
    comment = data.comment.strip()[:1000]
    if data.decision == "reject" and not comment:
        raise HTTPException(400, "Напишите, почему апелляция отклонена")
    if data.decision == "approve":
        unblock(db, a.user, comment or "Блокировка снята")
        a.status = "approved"
    else:
        a.status = "rejected"
    a.admin_comment = comment or a.admin_comment
    a.resolved_at = datetime.now()
    db.commit()
    return appeal_dict(a)


# ---------- отзывы ----------

def review_dict(r: Review):
    return {
        "id": r.id,
        "seller_id": r.seller_id,
        "seller": r.seller.name,
        "author_id": r.author_id,
        "author": r.author.name,
        "rating": r.rating,
        "text": r.text,
        "status": r.status,
        "created_at": r.created_at.isoformat(),
    }


@app.get("/api/reviews")
def api_reviews(status: str | None = None, db: Session = Depends(get_db)):
    query = select(Review).order_by(Review.created_at.desc(), Review.id.desc())
    if status:
        query = query.where(Review.status == status)
    return [review_dict(r) for r in db.scalars(query).all()]


@app.post("/api/reviews/{review_id}/status")
def api_set_review_status(review_id: int, data: StatusIn, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Отзыв не найден")
    if data.status not in REVIEW_STATUSES:
        raise HTTPException(400, "Неизвестный статус")
    r.status = data.status
    db.commit()
    return review_dict(r)


@app.delete("/api/reviews/{review_id}")
def api_delete_review(review_id: int, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Отзыв не найден")
    db.delete(r)
    db.commit()
    return {"ok": True}


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
