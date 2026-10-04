"""Конфигурация приложения «Скачки».

Все параметры читаются из переменных окружения. Благодаря этому один и тот же
исходный код разворачивается на стендах TEST / STAGE / PROD без изменений —
достаточно своего файла ``.env`` на каждой виртуальной машине
(см. лабораторную работу № 2 «Виртуализация»).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Корень репозитория: <repo>/app/config.py -> <repo>
BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DATABASE_URL = "sqlite:///instance/skachki.db"


def _env(name: str, default: str) -> str:
    """Прочитать переменную окружения; пустая строка трактуется как «не задано»."""
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on", "да"}


@dataclass(frozen=True)
class Settings:
    """Настройки стенда."""

    app_name: str
    stand: str
    database_url: str
    session_ttl_hours: int
    host: str
    port: int
    auto_seed: bool
    seed_demo_data: bool
    demo_login_hint: bool

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))

    @property
    def dialect_label(self) -> str:
        """Человекочитаемое имя СУБД — показывается в интерфейсе и в /api/health."""
        if self.is_sqlite:
            return "SQLite"
        if self.is_postgres:
            return "PostgreSQL"
        return self.database_url.split(":", 1)[0]

    @property
    def stand_label(self) -> str:
        return self.stand.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=_env("APP_NAME", "АС «Скачки»"),
        stand=_env("STAND_NAME", "local"),
        database_url=_env("DATABASE_URL", DEFAULT_DATABASE_URL),
        session_ttl_hours=_env_int("SESSION_TTL_HOURS", 12),
        host=_env("APP_HOST", "0.0.0.0"),
        port=_env_int("APP_PORT", 8080),
        auto_seed=_env_bool("AUTO_SEED", True),
        seed_demo_data=_env_bool("SEED_DEMO_DATA", True),
        demo_login_hint=_env_bool("DEMO_LOGIN_HINT", True),
    )


def reset_settings_cache() -> None:
    """Сбросить кэш настроек (используется в тестах)."""
    get_settings.cache_clear()
