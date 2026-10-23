from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    listings: Mapped[list["Listing"]] = relationship(back_populates="owner")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    listings: Mapped[list["Listing"]] = relationship(back_populates="category")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    want: Mapped[str] = mapped_column(String(200), default="")  # "Хочу взамен"
    city: Mapped[str] = mapped_column(String(100), default="")
    # active - активно, review - на проверке, blocked - заблокировано
    status: Mapped[str] = mapped_column(String(20), default="review")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="listings")
    category: Mapped["Category | None"] = relationship(back_populates="listings")
