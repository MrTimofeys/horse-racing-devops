"""Вход в систему и выход из неё."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import (
    SESSION_COOKIE,
    create_session,
    destroy_session,
    resolve_session,
)
from ..models import User
from ..security import verify_password
from ..web import redirect, render

router = APIRouter(tags=["Авторизация"])

settings = get_settings()

# Одно сообщение на все случаи отказа: не раскрываем, существует ли такой логин.
INVALID_CREDENTIALS = "Неверный логин или пароль"


@router.get("/login", summary="Форма входа")
def login_form(request: Request, db: Session = Depends(get_db)):
    user, _ = resolve_session(request, db)
    if user is not None:
        return redirect("/dashboard")
    return render(
        request,
        db,
        "login.html",
        username="",
        error=None,
        demo_hint=settings.demo_login_hint,
    )


@router.post("/login", summary="Аутентификация пользователя")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    login = username.strip()

    user = db.scalars(select(User).where(User.username == login)).first()

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return render(
            request,
            db,
            "login.html",
            username=login,
            error=INVALID_CREDENTIALS,
            demo_hint=settings.demo_login_hint,
            status_code=401,
        )

    token = create_session(db, user, request)
    response = redirect("/dashboard")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,   # cookie недоступна из JavaScript — защита от XSS-кражи сессии
        samesite="lax",  # защита от CSRF при переходах с внешних сайтов
        path="/",
    )
    return response


@router.post("/logout", summary="Выход из системы")
def logout(request: Request, db: Session = Depends(get_db)):
    _, session_row = resolve_session(request, db)
    destroy_session(db, session_row)

    response = redirect("/login")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
