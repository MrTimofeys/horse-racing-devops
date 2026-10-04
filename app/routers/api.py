"""JSON-API приложения «Скачки».

Используется для проверки работоспособности стенда (``/api/health``) и для
интеграции с внешними системами. Удобно для ЛР 2: после развёртывания стенда
достаточно одной команды ``curl``, чтобы подтвердить, что приложение поднялось.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__, crud
from ..config import get_settings
from ..database import get_db
from ..deps import require_user
from ..models import Hippodrome, Horse, Jockey, Owner, Race, RaceResult, User

router = APIRouter(prefix="/api", tags=["API"])

settings = get_settings()


# --- Сериализация ---------------------------------------------------------


def owner_json(owner: Owner) -> dict:
    return {
        "id": owner.id,
        "name": owner.name,
        "address": owner.address,
        "phone": owner.phone,
        "horses_count": len(owner.horses),
    }


def horse_json(horse: Horse) -> dict:
    return {
        "id": horse.id,
        "name": horse.name,
        "sex": horse.sex,
        "age": horse.age,
        "owner_id": horse.owner_id,
        "owner_name": horse.owner.name if horse.owner else None,
    }


def jockey_json(jockey: Jockey) -> dict:
    return {
        "id": jockey.id,
        "name": jockey.name,
        "address": jockey.address,
        "age": jockey.age,
        "rating": jockey.rating,
    }


def hippodrome_json(hippodrome: Hippodrome) -> dict:
    return {
        "id": hippodrome.id,
        "name": hippodrome.name,
        "city": hippodrome.city,
        "address": hippodrome.address,
    }


def result_json(result: RaceResult) -> dict:
    return {
        "id": result.id,
        "horse": {"id": result.horse_id, "name": result.horse.name if result.horse else None},
        "jockey": {"id": result.jockey_id, "name": result.jockey.name if result.jockey else None},
        "place": result.place,
        "finish_time_seconds": result.finish_time_seconds,
        "finish_time": result.time_label,
        "comment": result.comment,
    }


def race_json(race: Race, *, with_participants: bool = False) -> dict:
    payload = {
        "id": race.id,
        "title": race.display_title,
        "date": race.race_date.isoformat(),
        "time": race.race_time.strftime("%H:%M"),
        "status": race.status,
        "status_label": race.status_label,
        "hippodrome": hippodrome_json(race.hippodrome) if race.hippodrome else None,
        "participants_count": len(race.results),
        "finished_count": race.finished_count,
        "notes": race.notes,
    }
    if with_participants:
        payload["participants"] = [result_json(r) for r in race.participants]
    return payload


# --- Служебные ------------------------------------------------------------


@router.get("/health", summary="Проверка работоспособности стенда (без авторизации)")
def health(db: Session = Depends(get_db)):
    """Эндпоинт для мониторинга: отвечает всегда, даже если БД недоступна."""
    database_ok = True
    database_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - сообщаем о любой ошибке подключения
        database_ok = False
        database_error = str(exc)

    return {
        "status": "ok" if database_ok else "degraded",
        "application": settings.app_name,
        "version": __version__,
        "stand": settings.stand_label,
        "database": {"dialect": settings.dialect_label, "available": database_ok, "error": database_error},
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats", summary="Сводная статистика")
def stats(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return crud.dashboard_stats(db)


@router.get("/whoami", summary="Текущий пользователь API")
def whoami(user: User = Depends(require_user)):
    return {"username": user.username, "full_name": user.full_name, "role": user.role}


# --- Справочники ----------------------------------------------------------


@router.get("/owners", summary="Владельцы")
def api_owners(db: Session = Depends(get_db), user: User = Depends(require_user)):
    page = crud.list_owners(db, per_page=100)
    return {"total": page.total, "items": [owner_json(o) for o in page.items]}


@router.get("/horses", summary="Лошади")
def api_horses(db: Session = Depends(get_db), user: User = Depends(require_user)):
    page = crud.list_horses(db, per_page=100)
    return {"total": page.total, "items": [horse_json(h) for h in page.items]}


@router.get("/jockeys", summary="Жокеи")
def api_jockeys(db: Session = Depends(get_db), user: User = Depends(require_user)):
    page = crud.list_jockeys(db, per_page=100)
    return {"total": page.total, "items": [jockey_json(j) for j in page.items]}


@router.get("/hippodromes", summary="Ипподромы")
def api_hippodromes(db: Session = Depends(get_db), user: User = Depends(require_user)):
    page = crud.list_hippodromes(db, per_page=100)
    return {"total": page.total, "items": [hippodrome_json(h) for h in page.items]}


# --- Состязания -----------------------------------------------------------


@router.get("/races", summary="Состязания")
def api_races(
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    page = crud.list_races(db, status=status or None, per_page=100)
    return {"total": page.total, "items": [race_json(r) for r in page.items]}


@router.get("/races/{race_id}", summary="Состязание с составом и результатами (функция 1 ТЗ)")
def api_race(
    race_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    race = crud.load_race(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Состязание не найдено")
    return race_json(race, with_participants=True)
