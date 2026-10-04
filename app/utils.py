"""Вспомогательные функции: разбор и форматирование показанного времени, мест.

Пользователь вводит время заезда в привычном виде «минуты:секунды,сотые»
(например ``2:05,30``), а в базе оно хранится числом секунд — так его можно
сравнивать и сортировать, не прибегая к разбору строк в SQL.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

# «1:23,45» | «1:23.45» | «83,45» | «83.45» | «1:23»
# Секунды допускают три разряда: без минут «83,45» означает 83,45 секунды.
_RACE_TIME_RE = re.compile(
    r"^(?:(?P<minutes>\d{1,3}):)?(?P<seconds>\d{1,3})(?:[.,](?P<hundredths>\d{1,3}))?$"
)


class ValidationError(ValueError):
    """Ошибка валидации пользовательского ввода, пригодная для показа в форме."""


def parse_race_time(raw: str | None) -> float | None:
    """Преобразовать «2:05,30» в 125.3 секунды.

    Пустая строка и ``None`` дают ``None`` — время ещё не показано.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    match = _RACE_TIME_RE.match(text)
    if match is None:
        raise ValidationError(
            "Время укажите в формате «минуты:секунды,сотые», например 2:05,30"
        )

    seconds = int(match.group("seconds"))
    hundredths_raw = match.group("hundredths") or "0"
    # «45» трактуем как 45 сотых, «4» — как 40 сотых.
    hundredths = int(hundredths_raw.ljust(2, "0")[:2])

    minutes_raw = match.group("minutes")
    # Если минуты указаны явно, секунды обязаны быть в диапазоне 0–59.
    if minutes_raw is not None and seconds >= 60:
        raise ValidationError("Число секунд должно быть меньше 60")

    minutes = int(minutes_raw or 0)
    return round(minutes * 60 + seconds + hundredths / 100, 2)


def format_race_time(seconds: float | None) -> str:
    """Обратное преобразование: 125.3 -> «2:05,30». ``None`` -> «—»."""
    if seconds is None:
        return "—"
    whole = float(seconds)
    minutes, rest = divmod(whole, 60)
    return f"{int(minutes)}:{rest:05.2f}".replace(".", ",")


def format_place(place: int | None) -> str:
    """1 -> «1-е место», ``None`` -> «—» (результат ещё не внесён)."""
    if place is None:
        return "—"
    if 10 <= place % 100 <= 20:
        suffix = "е"
    else:
        suffix = {1: "е", 2: "е", 3: "е", 4: "е"}.get(place % 10, "е")
    return f"{place}-{suffix} место"


def parse_positive_int(
    raw: str | None,
    *,
    field: str,
    minimum: int = 1,
    maximum: int | None = None,
) -> int | None:
    """Разобрать целое число из формы с проверкой допустимого диапазона.

    Пустая строка даёт ``None`` — значение не задано.
    """
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValidationError(f"Поле «{field}» должно быть целым числом") from exc
    if value < minimum:
        raise ValidationError(f"Поле «{field}» не может быть меньше {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"Поле «{field}» не может быть больше {maximum}")
    return value


def parse_date(raw: str | None, *, field: str = "Дата") -> date:
    """Разобрать дату в формате ISO (``<input type="date">`` отдаёт именно его)."""
    if raw is None or not raw.strip():
        raise ValidationError(f"Поле «{field}» обязательно для заполнения")
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValidationError(f"Поле «{field}» должно быть датой в формате ГГГГ-ММ-ДД") from exc


def parse_time_of_day(raw: str | None, *, field: str = "Время") -> time:
    """Разобрать время суток в формате ЧЧ:ММ (``<input type="time">``)."""
    if raw is None or not raw.strip():
        raise ValidationError(f"Поле «{field}» обязательно для заполнения")
    text = raw.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValidationError(f"Поле «{field}» должно быть временем в формате ЧЧ:ММ")


def require_text(raw: str | None, *, field: str, max_length: int) -> str:
    """Обязательное текстовое поле с ограничением длины."""
    text = (raw or "").strip()
    if not text:
        raise ValidationError(f"Поле «{field}» обязательно для заполнения")
    if len(text) > max_length:
        raise ValidationError(f"Поле «{field}» не должно превышать {max_length} символов")
    return text


def optional_text(raw: str | None, *, max_length: int) -> str:
    """Необязательное текстовое поле с ограничением длины."""
    text = (raw or "").strip()
    if len(text) > max_length:
        raise ValidationError(f"Значение не должно превышать {max_length} символов")
    return text


def parse_choice(raw: str | None, *, field: str, allowed: tuple[str, ...]) -> str:
    """Проверить, что значение входит в список допустимых."""
    value = (raw or "").strip()
    if value not in allowed:
        raise ValidationError(
            f"Поле «{field}» должно принимать одно из значений: {', '.join(allowed)}"
        )
    return value


def plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 лошадь, 2 лошади, 5 лошадей."""
    if 10 <= count % 100 <= 20:
        form = many
    else:
        form = {1: one, 2: few, 3: few, 4: few}.get(count % 10, many)
    return f"{count} {form}"
