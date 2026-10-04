"""Поведение приложения при недоступной СУБД.

Актуально для стендов STAGE и PROD (ЛР 2): PostgreSQL может запускаться позже
службы приложения. Стенд обязан подняться и внятно сообщить о проблеме, а не
уходить в бесконечный перезапуск со стеком в журнале.

Недоступность СУБД моделируется без внешнего сервера: создаётся обычный файл, и
база указывается «внутри» него. Часть пути не является каталогом, поэтому SQLite
не может открыть базу и драйвер сообщает ``OperationalError``. Такой способ не
зависит от состояния файловой системы: каталога ``instance`` в репозитории нет,
он создаётся при первом запуске приложения.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app import database, main


def _engine_for(url: str):
    return create_engine(url, future=True, connect_args={"check_same_thread": False})


def _sessions_for(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _url_inside_a_file(tmp_path) -> str:
    """Строка подключения к базе «внутри» обычного файла — открыть её нельзя."""
    blocker = tmp_path / "blocker"
    blocker.write_text("обычный файл, а не каталог", encoding="utf-8")
    return f"sqlite:///{blocker}/skachki.db"


@pytest.fixture
def unavailable_database(monkeypatch, tmp_path):
    """Подменить текущую БД на недоступную."""
    broken_engine = _engine_for(_url_inside_a_file(tmp_path))
    broken_sessions = _sessions_for(broken_engine)

    monkeypatch.setattr(database, "engine", broken_engine)
    monkeypatch.setattr(database, "SessionLocal", broken_sessions)
    monkeypatch.setattr(main, "SessionLocal", broken_sessions)
    monkeypatch.setattr(database, "_schema_ready", False)
    return broken_engine


class TestDatabaseUnavailable:
    def test_stand_starts_without_database(self, unavailable_database, anon) -> None:
        """Приложение поднимается, несмотря на недоступную СУБД."""
        response = anon.get("/api/health")
        assert response.status_code == 200

    def test_health_reports_degraded(self, unavailable_database, anon) -> None:
        payload = anon.get("/api/health").json()
        assert payload["status"] == "degraded"
        assert payload["database"]["available"] is False
        assert payload["database"]["schema_ready"] is False
        assert payload["database"]["error"]
        assert payload["stand"] == "TEST"

    def test_page_with_database_access_returns_503(self, unavailable_database, anon) -> None:
        """Страница, которой нужна БД, отдаёт понятное объяснение, а не 500."""
        response = anon.get("/dashboard", cookies={"skachki_session": "any-token"})
        assert response.status_code == 503
        assert "База данных недоступна" in response.text

    def test_login_post_returns_503(self, unavailable_database, anon) -> None:
        response = anon.post("/login", data={"username": "admin", "password": "admin123"})
        assert response.status_code == 503
        assert "База данных недоступна" in response.text

    def test_api_returns_json_503(self, unavailable_database, anon) -> None:
        response = anon.get("/api/races", cookies={"skachki_session": "any-token"})
        assert response.status_code == 503
        payload = response.json()
        assert payload["detail"] == "База данных недоступна"
        assert payload["database"]["available"] is False

    def test_login_form_still_renders(self, unavailable_database, anon) -> None:
        """Страница входа не обращается к БД и остаётся доступной."""
        response = anon.get("/login")
        assert response.status_code == 200
        assert "Вход в систему" in response.text

    def test_repeated_requests_do_not_cascade(self, unavailable_database, anon) -> None:
        """Повторные обращения не приводят к рекурсии в обработчике ошибок."""
        for _ in range(3):
            assert anon.get("/dashboard", cookies={"skachki_session": "x"}).status_code == 503


class TestDatabaseRecovery:
    def test_schema_created_when_database_returns(
        self, unavailable_database, anon, monkeypatch, tmp_path
    ) -> None:
        """СУБД поднялась позже приложения — схема создаётся без перезапуска службы."""
        recovery_db = tmp_path / "recovery_test.db"
        recovery_db.unlink(missing_ok=True)

        assert anon.get("/api/health").json()["status"] == "degraded"

        recovered_engine = _engine_for(f"sqlite:///{recovery_db}")
        recovered_sessions = _sessions_for(recovered_engine)
        monkeypatch.setattr(database, "engine", recovered_engine)
        monkeypatch.setattr(database, "SessionLocal", recovered_sessions)
        monkeypatch.setattr(main, "SessionLocal", recovered_sessions)

        try:
            payload = anon.get("/api/health").json()
            assert payload["status"] == "ok", payload
            assert payload["database"]["available"] is True
            assert payload["database"]["schema_ready"] is True

            with recovered_engine.connect() as connection:
                tables = set(inspect(connection).get_table_names())

            assert {"users", "horses", "jockeys", "owners", "races", "race_results"} <= tables

            # Начальные данные тоже созданы: стенд сразу пригоден для входа.
            with recovered_sessions() as db:
                from app import crud

                assert crud.get_user_by_username(db, "admin") is not None
        finally:
            recovered_engine.dispose()
            recovery_db.unlink(missing_ok=True)
