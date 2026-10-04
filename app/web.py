"""Шаблоны, фильтры Jinja2 и вспомогательная функция отрисовки страниц."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import get_settings
from .deps import resolve_session
from .models import (
    HORSE_SEXES,
    RACE_STATUSES,
    RACE_STATUS_LABELS,
    USER_ROLES,
    USER_ROLE_LABELS,
)
from .utils import format_place, format_race_time, plural_ru

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Фильтры: {{ race.finish_time_seconds|race_time }}, {{ result.place|place }}
templates.env.filters["race_time"] = format_race_time
templates.env.filters["place"] = format_place
templates.env.filters["plural"] = plural_ru

# Справочники, доступные во всех шаблонах.
templates.env.globals.update(
    app_settings=get_settings(),
    HORSE_SEXES=HORSE_SEXES,
    RACE_STATUSES=RACE_STATUSES,
    RACE_STATUS_LABELS=RACE_STATUS_LABELS,
    USER_ROLES=USER_ROLES,
    USER_ROLE_LABELS=USER_ROLE_LABELS,
)


def flash(db: Session, session_row, level: str, text: str) -> None:  # noqa: ANN001
    """Запомнить сообщение, которое покажется после redirect (flash)."""
    if session_row is None:
        return
    session_row.flash = json.dumps([{"level": level, "text": text}], ensure_ascii=False)
    db.commit()


def flash_for(request: Request, db: Session, level: str, text: str) -> None:
    """Запомнить сообщение, самостоятельно найдя текущую сессию по cookie."""
    _, session_row = resolve_session(request, db)
    flash(db, session_row, level, text)


def render(
    request: Request,
    db: Session,
    template: str,
    *,
    status_code: int = 200,
    **context: Any,
):
    """Отрисовать HTML-страницу, добавив общий контекст (пользователь, сообщения, стенд)."""
    user, session_row = resolve_session(request, db)

    flashes: list[dict[str, str]] = list(context.pop("flashes", []))
    if session_row is not None and session_row.flash:
        try:
            flashes.extend(json.loads(session_row.flash))
        except (TypeError, ValueError):
            pass
        session_row.flash = ""
        db.commit()

    context.setdefault("user", user)
    context.setdefault("current_path", request.url.path)
    context["flashes"] = flashes
    context["settings"] = get_settings()

    return templates.TemplateResponse(
        request=request,
        name=template,
        context=context,
        status_code=status_code,
    )


def redirect(url: str) -> RedirectResponse:
    """POST -> redirect -> GET (PRG), чтобы F5 не повторял отправку формы."""
    return RedirectResponse(url=url, status_code=303)
