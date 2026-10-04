"""Зависимости FastAPI: определение текущего пользователя и проверка прав.

ТЗ (п. «Требования к защите информации от НСД»): компоненты подсистемы защиты
должны обеспечивать идентификацию пользователя и разграничение доступа
на уровне задач и информационных массивов.

Роли:
* ``viewer``   — только просмотр справочников и результатов;
* ``operator`` — добавление и изменение данных (справочники, состязания, результаты);
* ``admin``    — всё вышеперечисленное плюс удаление записей и управление учётными записями.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, UserSession
from .security import generate_session_token, hash_session_token

SESSION_COOKIE = "skachki_session"

settings = get_settings()


class LoginRequired(Exception):
    """Пользователь не авторизован. Обрабатывается редиректом на страницу входа."""


class Forbidden(Exception):
    """Прав недостаточно. Обрабатывается страницей 403."""

    def __init__(self, message: str = "Доступ запрещён") -> None:
        super().__init__(message)
        self.message = message


def resolve_session(request: Request, db: Session) -> tuple[User | None, UserSession | None]:
    """Найти активную сессию по cookie и вернуть (пользователь, сессия)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None, None

    stmt = select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    session_row = db.scalars(stmt).first()
    if session_row is None:
        return None, None

    # Просроченную сессию или сессию отключённого пользователя удаляем.
    if session_row.is_expired or not session_row.user.is_active:
        db.delete(session_row)
        db.commit()
        return None, None

    return session_row.user, session_row


def create_session(db: Session, user: User, request: Request) -> str:
    """Создать сессию и вернуть открытый токен (он же значение cookie)."""
    token = generate_session_token()
    db.add(
        UserSession(
            token_hash=hash_session_token(token),
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=settings.session_ttl_hours),
            client_ip=request.client.host if request.client else "",
        )
    )
    db.commit()
    return token


def destroy_session(db: Session, session_row: UserSession | None) -> None:
    if session_row is not None:
        db.delete(session_row)
        db.commit()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Текущий пользователь либо ``None`` (для страниц, доступных без входа)."""
    user, _ = resolve_session(request, db)
    return user


def require_user(user: User | None = Depends(get_current_user)) -> User:
    """Любой авторизованный пользователь."""
    if user is None:
        raise LoginRequired()
    return user


def require_editor(user: User = Depends(require_user)) -> User:
    """Пользователь, которому разрешено изменять данные."""
    if not user.can_edit:
        raise Forbidden("Недостаточно прав для изменения данных. Обратитесь к администратору.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """Администратор системы."""
    if not user.is_admin:
        raise Forbidden("Раздел доступен только администратору системы.")
    return user
