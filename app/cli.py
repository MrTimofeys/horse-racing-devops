"""Утилита командной строки для обслуживания АС «Скачки».

Примеры:

    python -m app.cli info                       # параметры текущего стенда
    python -m app.cli init-db                    # создать таблицы
    python -m app.cli seed --demo                # справочные данные + демо-набор
    python -m app.cli create-user --username ivan --password secret1 --role operator
    python -m app.cli set-password --username ivan --password newsecret
    python -m app.cli reset --yes                # полностью пересоздать схему
    python -m app.cli run --reload               # запустить сервер разработки
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from . import __version__, crud, seed
from .config import get_settings
from .database import SessionLocal, drop_db, engine, init_db
from .models import (
    Horse,
    Hippodrome,
    Jockey,
    Owner,
    Race,
    RaceResult,
    USER_ROLES,
    User,
)
from .utils import ValidationError

settings = get_settings()


def cmd_info(_args: argparse.Namespace) -> int:
    """Показать, с какой конфигурацией запущен стенд."""
    print(f"{settings.app_name} — версия {__version__}")
    print(f"  Стенд      : {settings.stand_label}")
    print(f"  СУБД       : {settings.dialect_label}")
    print(f"  DATABASE_URL: {settings.database_url}")
    print(f"  Адрес      : http://{settings.host}:{settings.port}")
    print(f"  Автосиды   : {settings.auto_seed} (демо-данные: {settings.seed_demo_data})")
    return 0


def cmd_init_db(_args: argparse.Namespace) -> int:
    init_db()
    print("Таблицы созданы (или уже существовали).")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    init_db()
    with SessionLocal() as db:
        created_users = seed.ensure_default_users(db)
        if created_users:
            print("Созданы учётные записи:", ", ".join(created_users))
        else:
            print("Учётные записи уже существуют.")

        if args.demo:
            if seed.is_empty(db) or args.force:
                seed.seed_demo_data(db)
                print("Демонстрационные данные загружены.")
            else:
                print("База не пуста, демо-данные пропущены (используйте --force).")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    init_db()
    with SessionLocal() as db:
        try:
            user = crud.create_user(
                db,
                username=args.username,
                password=args.password,
                full_name=args.full_name or "",
                role=args.role,
            )
        except ValidationError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            return 1
    print(f"Пользователь «{user.username}» создан (роль: {user.role_label}).")
    return 0


def cmd_set_password(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        user = crud.get_user_by_username(db, args.username)
        if user is None:
            print(f"Пользователь «{args.username}» не найден", file=sys.stderr)
            return 1
        crud.set_user_password(db, user, args.password)
    print(f"Пароль пользователя «{args.username}» изменён.")
    return 0


def cmd_list_users(_args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        users = crud.list_users(db, per_page=100).items
    if not users:
        print("Пользователей нет.")
        return 0
    print(f"{'логин':<16}{'роль':<16}{'активен':<10}имя")
    for user in users:
        print(f"{user.username:<16}{user.role_label:<16}{'да' if user.is_active else 'нет':<10}{user.full_name}")
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        rows = [
            ("Лошади", Horse),
            ("Владельцы", Owner),
            ("Жокеи", Jockey),
            ("Ипподромы", Hippodrome),
            ("Состязания", Race),
            ("Участники заездов", RaceResult),
            ("Пользователи", User),
        ]
        for label, model in rows:
            total = db.scalar(select(func.count()).select_from(model)) or 0
            print(f"  {label:<22}{total}")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    """Проверка подключения к СУБД — используется в скриптах развёртывания ЛР 2."""
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        print(f"База данных недоступна: {exc}", file=sys.stderr)
        return 1
    print(f"Подключение к {settings.dialect_label} установлено.")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        answer = input("Все данные будут удалены. Продолжить? [y/N] ").strip().lower()
        if answer not in {"y", "yes", "да", "д"}:
            print("Отменено.")
            return 1
    drop_db()
    init_db()
    with SessionLocal() as db:
        seed.ensure_default_users(db)
        if args.demo:
            seed.seed_demo_data(db)
    print("Схема пересоздана.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Обслуживание АС «Скачки»",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="показать параметры стенда").set_defaults(func=cmd_info)
    sub.add_parser("init-db", help="создать таблицы").set_defaults(func=cmd_init_db)
    sub.add_parser("stats", help="показать количество записей").set_defaults(func=cmd_stats)
    sub.add_parser("check", help="проверить подключение к СУБД").set_defaults(func=cmd_check)
    sub.add_parser("list-users", help="список пользователей").set_defaults(func=cmd_list_users)

    seed_parser = sub.add_parser("seed", help="создать учётные записи и демо-данные")
    seed_parser.add_argument("--demo", action="store_true", help="загрузить демонстрационные данные")
    seed_parser.add_argument("--force", action="store_true", help="загрузить демо-данные даже в непустую базу")
    seed_parser.set_defaults(func=cmd_seed)

    create_user = sub.add_parser("create-user", help="создать пользователя")
    create_user.add_argument("--username", required=True)
    create_user.add_argument("--password", required=True)
    create_user.add_argument("--role", choices=USER_ROLES, default="operator")
    create_user.add_argument("--full-name", default="")
    create_user.set_defaults(func=cmd_create_user)

    set_password = sub.add_parser("set-password", help="сменить пароль пользователя")
    set_password.add_argument("--username", required=True)
    set_password.add_argument("--password", required=True)
    set_password.set_defaults(func=cmd_set_password)

    reset = sub.add_parser("reset", help="пересоздать схему БД")
    reset.add_argument("--yes", action="store_true", help="не спрашивать подтверждение")
    reset.add_argument("--demo", action="store_true", help="загрузить демо-данные после сброса")
    reset.set_defaults(func=cmd_reset)

    run = sub.add_parser("run", help="запустить сервер приложения")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)
    run.add_argument("--reload", action="store_true", help="автоперезапуск при изменении кода")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    from sqlalchemy.exc import InterfaceError, OperationalError

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OperationalError, InterfaceError) as exc:
        # Понятное сообщение вместо трассировки: команда может вызываться из
        # скриптов развёртывания стендов (ЛР 2), где трассировка только мешает.
        print(f"База данных недоступна: {str(exc).splitlines()[0]}", file=sys.stderr)
        print(
            "Проверьте, что служба СУБД запущена, и строку DATABASE_URL.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
