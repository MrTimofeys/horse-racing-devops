"""Раздел «Результаты»: итоги заездов по всем состязаниям.

ТЗ (п. «Базовая подсистема») требует навигации между разделами «Состязания»,
«Жокеи», «Лошади», «Владельцы» и «Результаты». Этот раздел показывает занятые
места и показанное время по всем заездам сразу, с фильтрами и постранично.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..deps import require_user
from ..models import User
from ..web import render

router = APIRouter(prefix="/results", tags=["Результаты"])

# Справочников немного, поэтому для выпадающих списков берём одну страницу
# максимального размера: полная выгрузка данных ТЗ запрещена, но список
# ипподромов для фильтра целиком помещается в одну страницу.
_FILTER_PAGE = 100


@router.get("", summary="Результаты заездов (раздел «Результаты» ТЗ)")
def results_list(
    request: Request,
    search: str = "",
    hippodrome_id: int | None = None,
    show_declared: bool = False,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Итоги заездов: место и время по каждой лошади и жокею.

    По умолчанию показываются только те участники, чей результат уже внесён.
    Флажок «показать заявленных» добавляет лошадей, которые в заезде заявлены,
    но ещё не финишировали.
    """
    page_obj = crud.list_results(
        db,
        search=search,
        hippodrome_id=hippodrome_id,
        only_finished=not show_declared,
        page=page,
    )
    return render(
        request,
        db,
        "results/list.html",
        page_obj=page_obj,
        search=search,
        hippodrome_id=hippodrome_id,
        show_declared=show_declared,
        hippodromes=crud.list_hippodromes(db, page=1, per_page=_FILTER_PAGE).items,
    )
