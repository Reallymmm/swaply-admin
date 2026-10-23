from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal, get_db
from .models import User, Category, Listing
from .seed import seed

# папка frontend лежит рядом с папкой backend
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

STATUSES = ["active", "review", "blocked"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # при старте: создаём таблицы и кладём тестовые данные, если база пустая
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Swaply", lifespan=lifespan)

# CORS нужен, если фронт открыт с другого адреса (например, Live Server на :5500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- что приходит от фронта ----------

class StatusIn(BaseModel):
    status: str


class CategoryIn(BaseModel):
    name: str


# ---------- превращаем объекты базы в обычные словари для JSON ----------

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
        "created_at": x.created_at.isoformat(),
    }


def user_dict(u: User):
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "city": u.city,
        "is_blocked": u.is_blocked,
        "listings_count": len(u.listings),
        "created_at": u.created_at.isoformat(),
    }


# ---------- обзор ----------

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


# ---------- объявления ----------

@app.get("/api/listings")
def api_listings(status: str | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    query = select(Listing).order_by(Listing.created_at.desc(), Listing.id.desc())
    if status:
        query = query.where(Listing.status == status)
    if limit:
        query = query.limit(limit)
    return [listing_dict(x) for x in db.scalars(query).all()]


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


@app.post("/api/users/{user_id}/toggle-block")
def api_toggle_block(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.is_blocked = not user.is_blocked
    db.commit()
    return user_dict(user)


# ---------- категории ----------

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


# ---------- фронтенд ----------
# Эту строку держим В САМОМ КОНЦЕ: сначала ищутся /api/..., потом файлы из frontend
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
