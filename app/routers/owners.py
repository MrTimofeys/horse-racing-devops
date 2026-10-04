"""Справочник владельцев лошадей."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin, require_editor, require_user
from ..models import User
from ..utils import ValidationError, optional_text, require_text
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/owners", tags=["Владельцы"])

TEMPLATE_FORM = "owners/form.html"


@router.get("", summary="Список владельцев")
def owners_list(
    request: Request,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page_obj = crud.list_owners(db, search=search, page=page)
    return render(request, db, "owners/list.html", page_obj=page_obj, search=search)


@router.get("/new", summary="Форма добавления владельца")
def owner_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    return render(
        request,
        db,
        TEMPLATE_FORM,
        owner=None,
        data={"name": "", "address": "", "phone": ""},
        error=None,
    )


@router.post("/new", summary="Добавить владельца")
def owner_create(
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {"name": name, "address": address, "phone": phone}
    try:
        owner = crud.create_owner(
            db,
            name=require_text(name, field="Имя владельца", max_length=128),
            address=optional_text(address, max_length=255),
            phone=optional_text(phone, max_length=32),
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, owner=None, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Владелец «{owner.name}» добавлен")
    return redirect("/owners")


@router.get("/{owner_id}/edit", summary="Форма редактирования владельца")
def owner_edit(
    owner_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    owner = crud.get_owner(db, owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Владелец не найден")
    return render(
        request,
        db,
        TEMPLATE_FORM,
        owner=owner,
        data={"name": owner.name, "address": owner.address, "phone": owner.phone},
        error=None,
    )


@router.post("/{owner_id}/edit", summary="Сохранить владельца")
def owner_update(
    owner_id: int,
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    owner = crud.get_owner(db, owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Владелец не найден")

    data = {"name": name, "address": address, "phone": phone}
    try:
        crud.update_owner(
            db,
            owner,
            name=require_text(name, field="Имя владельца", max_length=128),
            address=optional_text(address, max_length=255),
            phone=optional_text(phone, max_length=32),
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, owner=owner, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Данные владельца «{owner.name}» сохранены")
    return redirect("/owners")


@router.post("/{owner_id}/delete", summary="Удалить владельца")
def owner_delete(
    owner_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    owner = crud.get_owner(db, owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Владелец не найден")

    name = owner.name
    try:
        crud.delete_owner(db, owner)
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect("/owners")

    flash_for(request, db, "success", f"Владелец «{name}» удалён")
    return redirect("/owners")
