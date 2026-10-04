"""Общие фикстуры для тестов АС «Скачки».

Переменные окружения выставляются ДО импорта приложения: конфигурация
и подключение к БД создаются на этапе импорта модулей ``app``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB_PATH = ROOT / "instance" / "test_skachki.db"

# Если DATABASE_URL задан извне, тесты выполняются на этой СУБД. Это позволяет
# прогнать весь набор и на PostgreSQL — так проверяется, что поведение стендов
# STAGE и PROD совпадает с поведением стенда TEST на SQLite:
#
#   DATABASE_URL="postgresql+psycopg://... " pytest
#
EXTERNAL_DATABASE_URL = os.environ.get("DATABASE_URL") or None

if not EXTERNAL_DATABASE_URL:
    # Присваиваем, а не setdefault: пустая строка в DATABASE_URL тоже должна
    # означать «использовать SQLite», а setdefault её бы не тронул.
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["STAND_NAME"] = "test"
os.environ["AUTO_SEED"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["DEMO_LOGIN_HINT"] = "true"
os.environ["SESSION_TTL_HOURS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.database import SessionLocal, drop_db, init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = ("admin", "admin123")
OPERATOR = ("operator", "operator123")
VIEWER = ("viewer", "viewer123")


@pytest.fixture(scope="session", autouse=True)
def database():
    """Чистая база на весь прогон тестов + демонстрационные данные."""
    if not EXTERNAL_DATABASE_URL and TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    # Начинаем с чистого листа: важно и для внешней СУБД, где могли остаться
    # таблицы от предыдущего запуска.
    drop_db()
    init_db()
    with SessionLocal() as db:
        seed.ensure_default_users(db)
        seed.seed_demo_data(db)
    yield
    drop_db()
    if not EXTERNAL_DATABASE_URL and TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def _login(client: TestClient, credentials: tuple[str, str]) -> TestClient:
    username, password = credentials
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303, f"Не удалось войти как {username}: {response.status_code}"
    assert "skachki_session" in response.cookies
    return client


@pytest.fixture
def anon() -> TestClient:
    """Клиент без авторизации."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin() -> TestClient:
    """Клиент с правами администратора."""
    with TestClient(app) as client:
        yield _login(client, ADMIN)


@pytest.fixture
def operator() -> TestClient:
    """Клиент с правами оператора (без права удаления)."""
    with TestClient(app) as client:
        yield _login(client, OPERATOR)


@pytest.fixture
def viewer() -> TestClient:
    """Клиент с правами только на просмотр."""
    with TestClient(app) as client:
        yield _login(client, VIEWER)


@pytest.fixture
def db():
    """Прямая сессия БД для проверок состояния после HTTP-запросов."""
    with SessionLocal() as session:
        yield session
