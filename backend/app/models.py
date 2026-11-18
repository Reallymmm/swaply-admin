from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Причины блокировки аккаунта (ключ хранится в БД, название показывается людям)
BAN_REASONS = {
    "spam": "Спам",
    "fraud": "Мошенничество",
    "abuse": "Оскорбления и неприемлемое поведение",
    "prohibited": "Запрещённые товары",
    "fake": "Фейковый аккаунт",
    "other": "Другое",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    token: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    avatar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ban_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)    # ключ из BAN_REASONS
    ban_comment: Mapped[str] = mapped_column(String(300), default="")
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    # active - активно, review - на проверке, blocked - заблокировано, hidden - скрыто автором
    status: Mapped[str] = mapped_column(String(20), default="review")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="listings")
    category: Mapped["Category | None"] = relationship(back_populates="listings")
    photos: Mapped[list["ListingPhoto"]] = relationship(
        back_populates="listing", order_by="ListingPhoto.id", cascade="all, delete-orphan"
    )


class ListingPhoto(Base):
    """Фотография объявления. Сам файл лежит в папке backend/uploads, тут только его имя."""
    __tablename__ = "listing_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    filename: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    listing: Mapped["Listing"] = relationship(back_populates="photos")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "listing_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))   # кто написал
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # владелец объявления
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    listing: Mapped["Listing"] = relationship()
    buyer: Mapped["User"] = relationship(foreign_keys=[buyer_id])
    seller: Mapped["User"] = relationship(foreign_keys=[seller_id])
    messages: Mapped[list["Message"]] = relationship(back_populates="chat", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    chat: Mapped["Chat"] = relationship(back_populates="messages")


class Review(Base):
    """Отзыв покупателя о продавце. Один пользователь - один отзыв на продавца (его можно изменить)."""
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("author_id", "seller_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # о ком отзыв
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # кто написал
    rating: Mapped[int] = mapped_column()                           # от 1 до 5
    text: Mapped[str] = mapped_column(Text, default="")
    # visible - виден всем, hidden - скрыт модератором (не виден и не влияет на рейтинг)
    status: Mapped[str] = mapped_column(String(20), default="visible", server_default="visible")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    seller: Mapped["User"] = relationship(foreign_keys=[seller_id])
    author: Mapped["User"] = relationship(foreign_keys=[author_id])


class Appeal(Base):
    """Апелляция заблокированного пользователя."""
    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    ban_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)  # за что заблокировали на момент подачи
    # pending - на рассмотрении, approved - одобрена, rejected - отклонена
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship()


class EmailCode(Base):
    """Код подтверждения почты при регистрации.
    Аккаунт создаётся только после ввода кода, а пока данные ждут здесь (пароль уже в виде хэша)."""
    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(200))
    code_hash: Mapped[str] = mapped_column(String(64))   # сам код не храним
    attempts: Mapped[int] = mapped_column(default=0)     # сколько раз ввели неверно
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Notification(Base):
    """Уведомление для пользователя мобильного приложения."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # message - новое сообщение в чате, listing_approved / listing_blocked - решение модерации
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(300), default="")
    chat_id: Mapped[int | None] = mapped_column(nullable=True)
    listing_id: Mapped[int | None] = mapped_column(nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
