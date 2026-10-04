"""Справочник жокеев, форма добавления и карточка с историей заездов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin, require_editor, require_user
from ..models import User
from ..utils import (
    ValidationError,
    optional_text,
    parse_positive_int,
    require_text,
)
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/jockeys", tags=["Жокеи"])

TEMPLATE_FORM = "jockeys/form.html"


@router.get("", summary="Список жокеев")
def jockeys_list(
    request: Request,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page_obj = crud.list_jockeys(db, search=search, page=page)
    return render(request, db, "jockeys/list.html", page_obj=page_obj, search=search)


@router.get("/new", summary="Форма добавления жокея")
def jockey_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    return render(
        request,
        db,
        TEMPLATE_FORM,
        jockey=None,
        data={"name": "", "address": "", "age": "", "rating": ""},
        error=None,
    )


@router.post("/new", summary="Добавить жокея (функция 3 ТЗ)")
def jockey_create(
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    age: str = Form(""),
    rating: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {"name": name, "address": address, "age": age, "rating": rating}
    try:
        jockey = crud.create_jockey(
            db,
            name=require_text(name, field="Имя жокея", max_length=128),
            address=optional_text(address, max_length=255),
            age=parse_positive_int(age, field="Возраст", minimum=16, maximum=99) or 0,
            rating=parse_positive_int(rating, field="Рейтинг", minimum=0, maximum=1000) or 0,
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, jockey=None, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Жокей «{jockey.name}» добавлен")
    return redirect("/jockeys")


@router.get("/{jockey_id}", summary="Карточка жокея и история его состязаний (функция 6 ТЗ)")
def jockey_detail(
    jockey_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    jockey = crud.get_jockey(db, jockey_id)
    if jockey is None:
        raise HTTPException(status_code=404, detail="Жокей не найден")
    return render(
        request, db, "jockeys/detail.html", jockey=jockey, history=crud.jockey_history(db, jockey)
    )


@router.get("/{jockey_id}/edit", summary="Форма редактирования жокея")
def jockey_edit(
    jockey_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    jockey = crud.get_jockey(db, jockey_id)
    if jockey is None:
        raise HTTPException(status_code=404, detail="Жокей не найден")
    return render(
        request,
        db,
        TEMPLATE_FORM,
        jockey=jockey,
        data={
            "name": jockey.name,
            "address": jockey.address,
            "age": str(jockey.age),
            "rating": str(jockey.rating),
        },
        error=None,
    )


@router.post("/{jockey_id}/edit", summary="Сохранить жокея")
def jockey_update(
    jockey_id: int,
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    age: str = Form(""),
    rating: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    jockey = crud.get_jockey(db, jockey_id)
    if jockey is None:
        raise HTTPException(status_code=404, detail="Жокей не найден")

    data = {"name": name, "address": address, "age": age, "rating": rating}
    try:
        crud.update_jockey(
            db,
            jockey,
            name=require_text(name, field="Имя жокея", max_length=128),
            address=optional_text(address, max_length=255),
            age=parse_positive_int(age, field="Возраст", minimum=16, maximum=99) or 0,
            rating=parse_positive_int(rating, field="Рейтинг", minimum=0, maximum=1000) or 0,
        )
    except ValidationError as exc:
        return render(request, db, TEMPLATE_FORM, jockey=jockey, data=data, error=str(exc), status_code=400)

    flash_for(request, db, "success", f"Данные жокея «{jockey.name}» сохранены")
    return redirect(f"/jockeys/{jockey.id}")


@router.post("/{jockey_id}/delete", summary="Удалить жокея")
def jockey_delete(
    jockey_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    jockey = crud.get_jockey(db, jockey_id)
    if jockey is None:
        raise HTTPException(status_code=404, detail="Жокей не найден")

    name = jockey.name
    try:
        crud.delete_jockey(db, jockey)
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect(f"/jockeys/{jockey_id}")

    flash_for(request, db, "success", f"Жокей «{name}» удалён")
    return redirect("/jockeys")
