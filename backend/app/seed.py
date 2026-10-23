from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import User, Category, Listing


def d(day, month=10):
    return datetime(2026, month, day, 12, 0)


def seed(db: Session):
    """Заполняет пустую базу тестовыми данными (один раз)."""
    if db.scalar(select(func.count()).select_from(User)) > 0:
        return

    users = [
        User(name="Анна Ковалёва", email="anna.k@mail.ru", city="Киров", created_at=d(12, 9)),
        User(name="Дмитрий Попов", email="dmitry.p@gmail.com", city="Киров", created_at=d(14, 9)),
        User(name="Мария Седова", email="maria.s@yandex.ru", city="Слободской", created_at=d(20, 9)),
        User(name="Илья Волков", email="ilya.v@gmail.com", city="Киров", created_at=d(28, 9)),
        User(name="Екатерина Лебедева", email="kate.l@mail.ru", city="Киров", created_at=d(30, 9), is_blocked=True),
        User(name="Олег Назаров", email="oleg.n@yandex.ru", city="Котельнич", created_at=d(2)),
    ]
    cats = {n: Category(name=n) for n in ["Одежда", "Техника", "Книги", "Игры", "Хобби", "Для дома"]}
    db.add_all(users + list(cats.values()))
    db.flush()  # чтобы у объектов появились id

    anna, dmitry, maria, ilya, kate, oleg = users
    listings = [
        Listing(title="Худи Nike, размер M", want="Джинсы или кроссовки", city="Киров",
                status="active", created_at=d(9), owner=anna, category=cats["Одежда"]),
        Listing(title="Игровая приставка PS4", want="Nintendo Switch", city="Киров",
                status="review", created_at=d(9), owner=dmitry, category=cats["Игры"]),
        Listing(title="Книги: «Мастер и Маргарита» + 3 романа", want="Любая фантастика", city="Слободской",
                status="active", created_at=d(8), owner=maria, category=cats["Книги"]),
        Listing(title="Беспроводные наушники JBL", want="Powerbank", city="Киров",
                status="active", created_at=d(8), owner=ilya, category=cats["Техника"]),
        Listing(title="Горный велосипед 26\"", want="Самокат или ролики", city="Котельнич",
                status="review", created_at=d(7), owner=oleg, category=cats["Хобби"]),
        Listing(title="Набор LEGO Technic", want="Настольные игры", city="Киров",
                status="blocked", created_at=d(6), owner=kate, category=cats["Хобби"]),
        Listing(title="Гитара акустическая", want="Укулеле", city="Киров",
                status="active", created_at=d(5), owner=dmitry, category=cats["Хобби"]),
        Listing(title="Куртка зимняя, размер L", want="Пуховик M", city="Киров",
                status="active", created_at=d(5), owner=anna, category=cats["Одежда"]),
    ]
    db.add_all(listings)
    db.commit()
