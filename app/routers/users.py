"""Управление учётными записями пользователей (только администратор)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin
from ..models import USER_ROLES, User
from ..utils import ValidationError, optional_text, parse_choice, require_text
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/users", tags=["Пользователи"])

TEMPLATE_FORM = "users/form.html"

MIN_PASSWORD_LENGTH = 6


def _validate_password(password: str, confirmation: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Пароль должен содержать не менее {MIN_PASSWORD_LENGTH} символов")
    if password != confirmation:
        raise ValidationError("Пароли не совпадают")
    return password


@router.get("", summary="Список пользователей")
def users_list(
    request: Request,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    page_obj = crud.list_users(db, search=search, page=page)
    return render(request, db, "users/list.html", page_obj=page_obj, search=search)


@router.get("/new", summary="Форма создания пользователя")
def user_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return render(
        request,
        db,
        TEMPLATE_FORM,
        edited=None,
        data={"username": "", "full_name": "", "role": "operator", "is_active": True},
        error=None,
    )


@router.post("/new", summary="Создать пользователя")
def user_create(
    request: Request,
    username: str = Form(""),
    full_name: str = Form(""),
    role: str = Form("operator"),
    password: str = Form(""),
    password2: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    data = {"username": username, "full_name": full_name, "role": role, "is_active": True}
    try:
        created = crud.create_user(
            db,
            username=require_text(username, field="Логин", max_length=64),
            password=_validate_password(password, password2),
            full_name=optional_text(full_name, max_length=128),
            role=parse_choice(role, field="Роль", allowed=USER_ROLES),
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, edited=None, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Пользователь «{created.username}» создан")
    return redirect("/users")


@router.get("/{user_id}/edit", summary="Форма редактирования пользователя")
def user_edit(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    edited = crud.get_user(db, user_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return render(
        request,
        db,
        TEMPLATE_FORM,
        edited=edited,
        data={
            "username": edited.username,
            "full_name": edited.full_name,
            "role": edited.role,
            "is_active": edited.is_active,
        },
        error=None,
    )


@router.post("/{user_id}/edit", summary="Сохранить пользователя")
def user_update(
    user_id: int,
    request: Request,
    full_name: str = Form(""),
    role: str = Form("operator"),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    edited = crud.get_user(db, user_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    active = is_active.strip().lower() in {"1", "true", "on", "yes", "да"}
    data = {
        "username": edited.username,
        "full_name": full_name,
        "role": role,
        "is_active": active,
    }
    try:
        crud.update_user(
            db,
            edited,
            full_name=optional_text(full_name, max_length=128),
            role=parse_choice(role, field="Роль", allowed=USER_ROLES),
            is_active=active,
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, edited=edited, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Учётная запись «{edited.username}» сохранена")
    return redirect("/users")


@router.get("/{user_id}/password", summary="Форма смены пароля")
def user_password_form(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    edited = crud.get_user(db, user_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return render(request, db, "users/password.html", edited=edited, error=None)


@router.post("/{user_id}/password", summary="Сменить пароль пользователя")
def user_password(
    user_id: int,
    request: Request,
    password: str = Form(""),
    password2: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    edited = crud.get_user(db, user_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    try:
        crud.set_user_password(db, edited, _validate_password(password, password2))
    except ValidationError as exc:
        return render(
            request, db, "users/password.html", edited=edited, error=str(exc), status_code=400
        )

    flash_for(request, db, "success", f"Пароль пользователя «{edited.username}» изменён")
    return redirect("/users")


@router.post("/{user_id}/delete", summary="Удалить пользователя")
def user_delete(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    edited = crud.get_user(db, user_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    username = edited.username
    try:
        crud.delete_user(db, edited, acting_user=user)
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect("/users")

    flash_for(request, db, "success", f"Пользователь «{username}» удалён")
    return redirect("/users")
