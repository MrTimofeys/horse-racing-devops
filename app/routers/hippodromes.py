"""Справочник ипподромов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin, require_editor, require_user
from ..models import User
from ..utils import ValidationError, optional_text, require_text
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/hippodromes", tags=["Ипподромы"])

TEMPLATE_FORM = "hippodromes/form.html"


@router.get("", summary="Список ипподромов")
def hippodromes_list(
    request: Request,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page_obj = crud.list_hippodromes(db, search=search, page=page)
    return render(request, db, "hippodromes/list.html", page_obj=page_obj, search=search)


@router.get("/new", summary="Форма добавления ипподрома")
def hippodrome_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    return render(
        request,
        db,
        TEMPLATE_FORM,
        hippodrome=None,
        data={"name": "", "city": "", "address": ""},
        error=None,
    )


@router.post("/new", summary="Добавить ипподром")
def hippodrome_create(
    request: Request,
    name: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {"name": name, "city": city, "address": address}
    try:
        hippodrome = crud.create_hippodrome(
            db,
            name=require_text(name, field="Название ипподрома", max_length=160),
            city=optional_text(city, max_length=128),
            address=optional_text(address, max_length=255),
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, hippodrome=None, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Ипподром «{hippodrome.name}» добавлен")
    return redirect("/hippodromes")


@router.get("/{hippodrome_id}/edit", summary="Форма редактирования ипподрома")
def hippodrome_edit(
    hippodrome_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    hippodrome = crud.get_hippodrome(db, hippodrome_id)
    if hippodrome is None:
        raise HTTPException(status_code=404, detail="Ипподром не найден")
    return render(
        request,
        db,
        TEMPLATE_FORM,
        hippodrome=hippodrome,
        data={"name": hippodrome.name, "city": hippodrome.city, "address": hippodrome.address},
        error=None,
    )


@router.post("/{hippodrome_id}/edit", summary="Сохранить ипподром")
def hippodrome_update(
    hippodrome_id: int,
    request: Request,
    name: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    hippodrome = crud.get_hippodrome(db, hippodrome_id)
    if hippodrome is None:
        raise HTTPException(status_code=404, detail="Ипподром не найден")

    data = {"name": name, "city": city, "address": address}
    try:
        crud.update_hippodrome(
            db,
            hippodrome,
            name=require_text(name, field="Название ипподрома", max_length=160),
            city=optional_text(city, max_length=128),
            address=optional_text(address, max_length=255),
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, hippodrome=hippodrome, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Ипподром «{hippodrome.name}» сохранён")
    return redirect("/hippodromes")


@router.post("/{hippodrome_id}/delete", summary="Удалить ипподром")
def hippodrome_delete(
    hippodrome_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    hippodrome = crud.get_hippodrome(db, hippodrome_id)
    if hippodrome is None:
        raise HTTPException(status_code=404, detail="Ипподром не найден")

    name = hippodrome.name
    try:
        crud.delete_hippodrome(db, hippodrome)
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect("/hippodromes")

    flash_for(request, db, "success", f"Ипподром «{name}» удалён")
    return redirect("/hippodromes")
