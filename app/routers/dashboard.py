"""Главная страница и сводка по системе."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_user
from ..models import User
from ..web import redirect, render

router = APIRouter(tags=["Главная"])


@router.get("/", include_in_schema=False)
def index():
    return redirect("/dashboard")


@router.get("/dashboard", summary="Сводка по системе")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    stats = crud.dashboard_stats(db)
    return render(
        request,
        db,
        "dashboard.html",
        stats=stats,
        upcoming=crud.upcoming_races(db),
        recent=crud.recent_races(db),
        top_jockeys=crud.top_jockeys(db),
    )
