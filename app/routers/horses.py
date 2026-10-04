"""Справочник лошадей, форма добавления и карточка с историей заездов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin, require_editor, require_user
from ..models import HORSE_SEXES, User
from ..utils import (
    ValidationError,
    optional_text,
    parse_choice,
    parse_positive_int,
    require_text,
)
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/horses", tags=["Лошади"])

TEMPLATE_FORM = "horses/form.html"


def _owner_choices(db: Session):
    """Все владельцы для выпадающего списка (их немного, пагинация не нужна)."""
    return crud.list_owners(db, page=1, per_page=100).items


def _parse_owner_id(raw: str) -> int | None:
    if not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValidationError("Некорректный владелец") from exc


@router.get("", summary="Список лошадей")
def horses_list(
    request: Request,
    search: str = "",
    owner_id: int | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page_obj = crud.list_horses(db, search=search, owner_id=owner_id, page=page)
    return render(
        request,
        db,
        "horses/list.html",
        page_obj=page_obj,
        search=search,
        owner_id=owner_id,
        owners=_owner_choices(db),
    )


@router.get("/new", summary="Форма добавления лошади")
def horse_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    return render(
        request,
        db,
        TEMPLATE_FORM,
        horse=None,
        data={"name": "", "sex": HORSE_SEXES[0], "age": "", "owner_id": ""},
        owners=_owner_choices(db),
        error=None,
    )


@router.post("/new", summary="Добавить лошадь")
def horse_create(
    request: Request,
    name: str = Form(""),
    sex: str = Form(""),
    age: str = Form(""),
    owner_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {"name": name, "sex": sex, "age": age, "owner_id": owner_id}
    try:
        horse = crud.create_horse(
            db,
            name=require_text(name, field="Кличка", max_length=128),
            sex=parse_choice(sex, field="Пол", allowed=HORSE_SEXES),
            age=parse_positive_int(age, field="Возраст", maximum=39) or 0,
            owner_id=_parse_owner_id(owner_id),
        )
    except ValidationError as exc:
        return render(
            request, db, TEMPLATE_FORM, horse=None, data=data,
            owners=_owner_choices(db), error=str(exc), status_code=400,
        )

    flash_for(request, db, "success", f"Лошадь «{horse.name}» добавлена")
    return redirect("/horses")


@router.get("/{horse_id}", summary="Карточка лошади и история её состязаний (функция 7 ТЗ)")
def horse_detail(
    horse_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    horse = crud.get_horse(db, horse_id)
    if horse is None:
        raise HTTPException(status_code=404, detail="Лошадь не найдена")
    return render(request, db, "horses/detail.html", horse=horse, history=crud.horse_history(db, horse))


@router.get("/{horse_id}/edit", summary="Форма редактирования лошади")
def horse_edit(
    horse_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    horse = crud.get_horse(db, horse_id)
    if horse is None:
        raise HTTPException(status_code=404, detail="Лошадь не найдена")
    return render(
        request,
        db,
        TEMPLATE_FORM,
        horse=horse,
        data={
            "name": horse.name,
            "sex": horse.sex,
            "age": str(horse.age),
            "owner_id": str(horse.owner_id or ""),
        },
        owners=_owner_choices(db),
        error=None,
    )


@router.post("/{horse_id}/edit", summary="Сохранить лошадь")
def horse_update(
    horse_id: int,
    request: Request,
    name: str = Form(""),
    sex: str = Form(""),
    age: str = Form(""),
    owner_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    horse = crud.get_horse(db, horse_id)
    if horse is None:
        raise HTTPException(status_code=404, detail="Лошадь не найдена")

    data = {"name": name, "sex": sex, "age": age, "owner_id": owner_id}
    try:
        crud.update_horse(
            db,
            horse,
            name=require_text(name, field="Кличка", max_length=128),
            sex=parse_choice(sex, field="Пол", allowed=HORSE_SEXES),
            age=parse_positive_int(age, field="Возраст", maximum=39) or 0,
            owner_id=_parse_owner_id(owner_id),
        )
    except ValidationError as exc:
        return render(
            request, db, TEMPLATE_FORM, horse=horse, data=data,
            owners=_owner_choices(db), error=str(exc), status_code=400,
        )

    flash_for(request, db, "success", f"Данные лошади «{horse.name}» сохранены")
    return redirect(f"/horses/{horse.id}")


@router.post("/{horse_id}/delete", summary="Удалить лошадь")
def horse_delete(
    horse_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    horse = crud.get_horse(db, horse_id)
    if horse is None:
        raise HTTPException(status_code=404, detail="Лошадь не найдена")

    name = horse.name
    try:
        crud.delete_horse(db, horse)
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect(f"/horses/{horse_id}")

    flash_for(request, db, "success", f"Лошадь «{name}» удалена")
    return redirect("/horses")
