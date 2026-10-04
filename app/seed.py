"""Начальное наполнение базы данных.

При первом запуске приложение создаёт учётные записи и демонстрационный
набор данных, чтобы стенд TEST можно было проверить сразу после развёртывания
(см. ЛР 2, п. 5 «развернуть средства разработки и запустить прототип»).

Демо-данные не затрагивают существующие записи: они добавляются только в том
случае, если справочник ипподромов пуст.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud
from .config import get_settings
from .models import (
    RACE_FINISHED,
    RACE_PLANNED,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    Horse,
    Hippodrome,
    Jockey,
    Owner,
    Race,
    User,
)
from .security import hash_password

settings = get_settings()

# Демонстрационные учётные записи. Пароли совпадают с логинами + «123».
# На стендах, доступных извне, пароли обязательно меняются (см. README).
DEFAULT_USERS: tuple[dict[str, str], ...] = (
    {"username": "admin", "password": "admin123", "full_name": "Администратор системы", "role": ROLE_ADMIN},
    {"username": "operator", "password": "operator123", "full_name": "Оператор клуба", "role": ROLE_OPERATOR},
    {"username": "viewer", "password": "viewer123", "full_name": "Наблюдатель", "role": ROLE_VIEWER},
)


def ensure_default_users(db: Session) -> list[str]:
    """Создать отсутствующие демонстрационные учётные записи."""
    created: list[str] = []
    for spec in DEFAULT_USERS:
        if crud.get_user_by_username(db, spec["username"]) is not None:
            continue
        db.add(
            User(
                username=spec["username"],
                password_hash=hash_password(spec["password"]),
                full_name=spec["full_name"],
                role=spec["role"],
                is_active=True,
            )
        )
        created.append(spec["username"])
    if created:
        db.commit()
    return created


def is_empty(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(Hippodrome)) or 0) == 0


def seed_demo_data(db: Session) -> None:
    """Наполнить пустую базу демонстрационным набором данных."""
    hippodromes = [
        Hippodrome(name="Центральный московский ипподром", city="Москва", address="Беговая аллея, 22"),
        Hippodrome(name="Казанский ипподром", city="Казань", address="ул. Патриса Лумумбы, 47"),
        Hippodrome(name="Пятигорский ипподром", city="Пятигорск", address="ул. Козлова, 1"),
    ]
    db.add_all(hippodromes)

    owners = [
        Owner(name="Смирнов Алексей Петрович", address="г. Москва, ул. Лесная, 12", phone="+7 (916) 111-22-33"),
        Owner(name="Кузнецова Мария Ивановна", address="г. Казань, ул. Баумана, 5", phone="+7 (917) 222-33-44"),
        Owner(name="ООО «Копыто и седло»", address="г. Москва, ул. Умные студенты, 13", phone="+7 (495) 967-77-77"),
        Owner(name="Гарин Тимур Русланович", address="г. Пятигорск, пр. Кирова, 40", phone="+7 (918) 333-44-55"),
    ]
    db.add_all(owners)
    db.flush()  # нужны идентификаторы для ссылок

    horses = [
        Horse(name="Ветер Перемен", sex="жеребец", age=5, owner_id=owners[0].id),
        Horse(name="Алая Заря", sex="кобыла", age=4, owner_id=owners[0].id),
        Horse(name="Бархат", sex="мерин", age=7, owner_id=owners[1].id),
        Horse(name="Гроза Востока", sex="кобыла", age=6, owner_id=owners[1].id),
        Horse(name="Дон Кихот", sex="жеребец", age=3, owner_id=owners[2].id),
        Horse(name="Енисей", sex="жеребец", age=8, owner_id=owners[2].id),
        Horse(name="Жемчужина", sex="кобыла", age=5, owner_id=owners[3].id),
        Horse(name="Звёздный Час", sex="мерин", age=6, owner_id=owners[3].id),
    ]
    db.add_all(horses)

    jockeys = [
        Jockey(name="Иванов Пётр Сергеевич", address="г. Москва, ул. Спортивная, 3", age=29, rating=87),
        Jockey(name="Ахметов Рустам Ильдарович", address="г. Казань, ул. Профсоюзная, 18", age=32, rating=91),
        Jockey(name="Волкова Анна Дмитриевна", address="г. Москва, Ленинский пр-т, 74", age=26, rating=78),
        Jockey(name="Дорохов Илья Андреевич", address="г. Пятигорск, ул. Мира, 9", age=35, rating=84),
        Jockey(name="Соколов Максим Олегович", address="г. Москва, ул. Беговая, 21", age=24, rating=69),
        Jockey(name="Ткачёва Ольга Викторовна", address="г. Казань, ул. Достоевского, 52", age=30, rating=81),
    ]
    db.add_all(jockeys)
    db.flush()

    today = date.today()

    races = [
        Race(
            title="Кубок открытия сезона",
            race_date=today - timedelta(days=21),
            race_time=time(14, 0),
            hippodrome_id=hippodromes[0].id,
            status=RACE_FINISHED,
            notes="Дистанция 2000 м, грунт.",
        ),
        Race(
            title="Приз «Большой всероссийский»",
            race_date=today - timedelta(days=7),
            race_time=time(15, 30),
            hippodrome_id=hippodromes[1].id,
            status=RACE_FINISHED,
            notes="Дистанция 2400 м, песчаная дорожка.",
        ),
        Race(
            title="Летнее дерби",
            race_date=today + timedelta(days=10),
            race_time=time(13, 45),
            hippodrome_id=hippodromes[0].id,
            status=RACE_PLANNED,
            notes="Дистанция 1600 м.",
        ),
        Race(
            title="Мемориал Пятигорска",
            race_date=today + timedelta(days=24),
            race_time=time(16, 0),
            hippodrome_id=hippodromes[2].id,
            status=RACE_PLANNED,
            notes="Дистанция 2800 м.",
        ),
    ]
    db.add_all(races)
    db.flush()

    # Завершённые заезды — с местами и показанным временем.
    db.add_all(
        [
            # Кубок открытия сезона
            _result(races[0].id, horses[0].id, jockeys[1].id, 1, 125.30),
            _result(races[0].id, horses[2].id, jockeys[0].id, 2, 126.05),
            _result(races[0].id, horses[4].id, jockeys[3].id, 3, 127.40),
            _result(races[0].id, horses[6].id, jockeys[2].id, 4, 128.10),
            # Приз «Большой всероссийский»
            _result(races[1].id, horses[5].id, jockeys[3].id, 1, 150.75),
            _result(races[1].id, horses[1].id, jockeys[2].id, 2, 151.20),
            _result(races[1].id, horses[3].id, jockeys[5].id, 3, 152.00),
            # Предстоящие заезды — заявленный состав без результатов.
            _result(races[2].id, horses[0].id, jockeys[0].id),
            _result(races[2].id, horses[1].id, jockeys[2].id),
            _result(races[2].id, horses[6].id, jockeys[4].id),
            _result(races[3].id, horses[2].id, jockeys[3].id),
            _result(races[3].id, horses[7].id, jockeys[5].id),
        ]
    )

    db.commit()


def _result(race_id: int, horse_id: int, jockey_id: int, place: int | None = None, seconds: float | None = None):
    from .models import RaceResult

    return RaceResult(
        race_id=race_id,
        horse_id=horse_id,
        jockey_id=jockey_id,
        place=place,
        finish_time_seconds=seconds,
    )


def bootstrap(db: Session) -> dict[str, object]:
    """Выполнить инициализацию при старте приложения.

    * учётные записи создаются всегда, если их нет;
    * демонстрационные данные — только на пустой базе и при SEED_DEMO_DATA=true.
    """
    summary: dict[str, object] = {"users_created": [], "demo_data": False}

    if not settings.auto_seed:
        return summary

    summary["users_created"] = ensure_default_users(db)

    if settings.seed_demo_data and is_empty(db):
        seed_demo_data(db)
        summary["demo_data"] = True

    return summary
