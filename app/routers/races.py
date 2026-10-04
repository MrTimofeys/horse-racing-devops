"""Состязания: список, карточка заезда, состав участников и результаты.

Здесь реализованы функции ТЗ:
* 1 — список участвующих жокеев и лошадей с местами и временем (карточка заезда);
* 2 — добавление нового состязания;
* 5 — добавление результатов прошедшего состязания.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_admin, require_editor, require_user
from ..models import (
    RACE_PLANNED,
    RACE_STATUSES,
    User,
)
from ..utils import (
    ValidationError,
    optional_text,
    parse_choice,
    parse_date,
    parse_positive_int,
    parse_race_time,
    parse_time_of_day,
)
from ..web import flash_for, redirect, render

router = APIRouter(prefix="/races", tags=["Состязания"])

TEMPLATE_FORM = "races/form.html"


def _hippodrome_choices(db: Session):
    return crud.list_hippodromes(db, page=1, per_page=100).items


def _race_form_context(db: Session, *, race, data, error=None) -> dict:
    return {
        "race": race,
        "data": data,
        "error": error,
        "hippodromes": _hippodrome_choices(db),
        "statuses": RACE_STATUSES,
    }


@router.get("", summary="Список состязаний")
def races_list(
    request: Request,
    search: str = "",
    status: str = "",
    hippodrome_id: int | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page_obj = crud.list_races(
        db,
        search=search,
        status=status or None,
        hippodrome_id=hippodrome_id,
        page=page,
    )
    return render(
        request,
        db,
        "races/list.html",
        page_obj=page_obj,
        search=search,
        status=status,
        hippodrome_id=hippodrome_id,
        hippodromes=_hippodrome_choices(db),
    )


@router.get("/new", summary="Форма добавления состязания")
def race_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {
        "title": "",
        "race_date": "",
        "race_time": "",
        "hippodrome_id": "",
        "status": RACE_PLANNED,
        "notes": "",
    }
    return render(
        request, db, TEMPLATE_FORM, **_race_form_context(db, race=None, data=data)
    )


@router.post("/new", summary="Добавить состязание (функция 2 ТЗ)")
def race_create(
    request: Request,
    title: str = Form(""),
    race_date: str = Form(""),
    race_time: str = Form(""),
    hippodrome_id: str = Form(""),
    status: str = Form(RACE_PLANNED),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    data = {
        "title": title,
        "race_date": race_date,
        "race_time": race_time,
        "hippodrome_id": hippodrome_id,
        "status": status,
        "notes": notes,
    }
    try:
        race = crud.create_race(
            db,
            title=optional_text(title, max_length=160),
            race_date=parse_date(race_date, field="Дата"),
            race_time=parse_time_of_day(race_time, field="Время"),
            hippodrome_id=int(hippodrome_id) if hippodrome_id.strip() else 0,
            status=parse_choice(status, field="Статус", allowed=RACE_STATUSES),
            notes=optional_text(notes, max_length=2000),
        )
    except ValidationError as exc:
        return render(
            request,
            db,
            TEMPLATE_FORM,
            status_code=400,
            **_race_form_context(db, race=None, data=data, error=str(exc)),
        )
    except ValueError:
        return render(
            request,
            db,
            TEMPLATE_FORM,
            status_code=400,
            **_race_form_context(db, race=None, data=data, error="Выберите ипподром из списка"),
        )

    flash_for(request, db, "success", f"Состязание «{race.display_title}» добавлено")
    return redirect(f"/races/{race.id}")


@router.get("/{race_id}", summary="Карточка заезда: состав, места и время (функция 1 ТЗ)")
def race_detail(
    race_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    race = crud.load_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")
    return render(
        request,
        db,
        "races/detail.html",
        race=race,
        horses=crud.get_horse_options(db),
        jockeys=crud.get_jockey_options(db),
    )


@router.get("/{race_id}/edit", summary="Форма редактирования состязания")
def race_edit(
    race_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")
    data = {
        "title": race.title,
        "race_date": race.race_date.isoformat(),
        "race_time": race.race_time.strftime("%H:%M"),
        "hippodrome_id": str(race.hippodrome_id),
        "status": race.status,
        "notes": race.notes,
    }
    return render(request, db, TEMPLATE_FORM, **_race_form_context(db, race=race, data=data))


@router.post("/{race_id}/edit", summary="Сохранить состязание")
def race_update(
    race_id: int,
    request: Request,
    title: str = Form(""),
    race_date: str = Form(""),
    race_time: str = Form(""),
    hippodrome_id: str = Form(""),
    status: str = Form(RACE_PLANNED),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")

    data = {
        "title": title,
        "race_date": race_date,
        "race_time": race_time,
        "hippodrome_id": hippodrome_id,
        "status": status,
        "notes": notes,
    }
    try:
        crud.update_race(
            db,
            race,
            title=optional_text(title, max_length=160),
            race_date=parse_date(race_date, field="Дата"),
            race_time=parse_time_of_day(race_time, field="Время"),
            hippodrome_id=int(hippodrome_id),
            status=parse_choice(status, field="Статус", allowed=RACE_STATUSES),
            notes=optional_text(notes, max_length=2000),
        )
    except (ValidationError, ValueError) as exc:
        error = str(exc) if isinstance(exc, ValidationError) else "Выберите ипподром из списка"
        return render(
            request,
            db,
            TEMPLATE_FORM,
            status_code=400,
            **_race_form_context(db, race=race, data=data, error=error),
        )

    flash_for(request, db, "success", "Изменения состязания сохранены")
    return redirect(f"/races/{race.id}")


@router.post("/{race_id}/delete", summary="Удалить состязание")
def race_delete(
    race_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")

    title = race.display_title
    crud.delete_race(db, race)
    flash_for(request, db, "success", f"Состязание «{title}» удалено вместе с составом заезда")
    return redirect("/races")


@router.post("/{race_id}/participants", summary="Заявить участника заезда / внести результат (функция 5 ТЗ)")
def race_add_participant(
    race_id: int,
    request: Request,
    horse_id: str = Form(""),
    jockey_id: str = Form(""),
    place: str = Form(""),
    finish_time: str = Form(""),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")

    try:
        if not horse_id.strip():
            raise ValidationError("Выберите лошадь")
        if not jockey_id.strip():
            raise ValidationError("Выберите жокея")
        crud.add_participant(
            db,
            race,
            horse_id=int(horse_id),
            jockey_id=int(jockey_id),
            place=parse_positive_int(place, field="Занятое место", maximum=99),
            finish_time_seconds=parse_race_time(finish_time),
            comment=optional_text(comment, max_length=255),
        )
    except (ValidationError, ValueError) as exc:
        flash_for(request, db, "error", str(exc))
        return redirect(f"/races/{race_id}")

    flash_for(request, db, "success", "Участник заезда добавлен")
    return redirect(f"/races/{race_id}")


@router.post("/{race_id}/results/{result_id}", summary="Внести результат участника заезда")
def race_update_result(
    race_id: int,
    result_id: int,
    request: Request,
    place: str = Form(""),
    finish_time: str = Form(""),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    result = crud.get_result(db, result_id)
    if result is None or result.race_id != race_id:
        raise HTTPException(status_code=404, detail="Участник заезда не найден")

    try:
        crud.update_result(
            db,
            result,
            place=parse_positive_int(place, field="Занятое место", maximum=99),
            finish_time_seconds=parse_race_time(finish_time),
            comment=optional_text(comment, max_length=255),
        )
    except ValidationError as exc:
        flash_for(request, db, "error", str(exc))
        return redirect(f"/races/{race_id}")

    flash_for(request, db, "success", "Результат сохранён")
    return redirect(f"/races/{race_id}")


@router.post("/{race_id}/results/{result_id}/delete", summary="Убрать участника из заезда")
def race_remove_participant(
    race_id: int,
    result_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    result = crud.get_result(db, result_id)
    if result is None or result.race_id != race_id:
        raise HTTPException(status_code=404, detail="Участник заезда не найден")

    crud.remove_participant(db, result)
    flash_for(request, db, "success", "Участник убран из заезда")
    return redirect(f"/races/{race_id}")


@router.post("/{race_id}/finish", summary="Отметить состязание завершённым")
def race_finish(
    race_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")

    crud.finish_race(db, race)
    flash_for(request, db, "success", "Состязание отмечено завершённым")
    return redirect(f"/races/{race_id}")


@router.post("/{race_id}/cancel", summary="Отменить состязание")
def race_cancel(
    race_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    race = crud.get_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")

    crud.cancel_race(db, race)
    flash_for(request, db, "success", "Состязание отменено")
    return redirect(f"/races/{race_id}")
