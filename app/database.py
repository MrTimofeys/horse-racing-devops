"""Подключение к базе данных и создание схемы.

ТЗ (п. «Требования к информационному обеспечению»): хранение данных
осуществляется на основе реляционных СУБД. Поддерживаются SQLite
(по умолчанию, для быстрого развёртывания) и PostgreSQL (через DATABASE_URL).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import BASE_DIR, get_settings

settings = get_settings()


def _prepare_sqlite_directory(url: str) -> None:
    """Создать каталог для файла БД, иначе SQLite не сможет его открыть."""
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.removeprefix("sqlite:///")
    if not raw_path or raw_path == ":memory:":
        return
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)


_prepare_sqlite_directory(settings.database_url)

_connect_args: dict[str, object] = {}
if settings.is_sqlite:
    # FastAPI обслуживает запросы в пуле потоков, поэтому запрет на общий
    # коннект между потоками нужно снять.
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)


def _sqlite_lower(value):  # noqa: ANN001, ANN201
    return value.lower() if isinstance(value, str) else value


def _sqlite_upper(value):  # noqa: ANN001, ANN201
    return value.upper() if isinstance(value, str) else value


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Настроить соединение SQLite.

    Во-первых, включить контроль внешних ключей: без этого SQLite молча
    игнорирует ON DELETE CASCADE и ссылочную целостность, а ТЗ требует
    обеспечения целостности данных средствами СУБД.

    Во-вторых, заменить встроенные функции ``lower`` и ``upper`` на версии
    Python. Встроенные функции SQLite обрабатывают только латиницу: запрос
    ``lower('Иванов')`` возвращает ``'Иванов'``. Из-за этого поиск без учёта
    регистра по русскому тексту на SQLite не работает, тогда как в PostgreSQL
    функции зависят от языка и работают правильно. Стенд TEST вёл бы себя иначе,
    чем STAGE и PROD, поэтому функции переопределяются.
    """
    if not settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    dbapi_connection.create_function("lower", 1, _sqlite_lower, deterministic=True)
    dbapi_connection.create_function("upper", 1, _sqlite_upper, deterministic=True)


class Base(DeclarativeBase):
    """Базовый класс всех ORM-моделей."""


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия БД на время обработки одного запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создать отсутствующие таблицы."""
    from . import models  # noqa: F401  — регистрирует модели в Base.metadata

    Base.metadata.create_all(bind=engine)


# --- Состояние готовности схемы -------------------------------------------
#
# На стендах STAGE и PROD приложение работает с PostgreSQL, который может
# подниматься дольше, чем служба приложения. Поэтому факт успешного создания
# схемы запоминается: если СУБД была недоступна при старте, схема будет
# создана при первой удачной проверке работоспособности (см. /api/health).

_schema_ready = False


def schema_ready() -> bool:
    """True, если схема БД успешно создана в текущем процессе."""
    return _schema_ready


def mark_schema_ready() -> None:
    global _schema_ready
    _schema_ready = True


def drop_db() -> None:
    """Удалить все таблицы (используется в тестах и при сбросе стенда)."""
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
