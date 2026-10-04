"""Постраничный вывод списков.

ТЗ (п. «Требования к информационному обеспечению»): структура базы данных
должна исключать единовременную полную выгрузку информации. Поэтому все
справочники и списки состязаний отдаются страницами.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


@dataclass
class Page(Generic[T]):
    """Одна страница результатов вместе с метаданными для пагинатора."""

    items: list[T]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        if self.per_page <= 0:
            return 1
        return max(1, -(-self.total // self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_page(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        return min(self.pages, self.page + 1)

    @property
    def first_index(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        return min(self.total, self.page * self.per_page)


def normalize_page(page: int | None) -> int:
    return max(1, page or 1)


def normalize_per_page(per_page: int | None) -> int:
    if not per_page:
        return DEFAULT_PER_PAGE
    return min(MAX_PER_PAGE, max(1, per_page))


def paginate(db: Session, stmt: Select, *, page: int | None, per_page: int | None) -> Page:
    """Выполнить запрос постранично, посчитав общее количество строк."""
    page = normalize_page(page)
    per_page = normalize_per_page(per_page)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(
        db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).unique().all()
    )
    return Page(items=items, total=total, page=page, per_page=per_page)
