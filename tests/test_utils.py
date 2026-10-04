"""Проверка вспомогательных функций и модуля безопасности."""

from __future__ import annotations

import pytest

from app.security import hash_password, hash_session_token, verify_password
from app.utils import (
    ValidationError,
    format_place,
    format_race_time,
    parse_date,
    parse_positive_int,
    parse_race_time,
    parse_time_of_day,
    plural_ru,
)


class TestRaceTime:
    """Показанное время заезда: ввод в формате «минуты:секунды,сотые»."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2:05,30", 125.30),
            ("2:05.30", 125.30),
            ("1:23,45", 83.45),
            ("83,45", 83.45),
            ("83.45", 83.45),
            ("1:23", 83.0),
            ("0:59,99", 59.99),
            ("10:00", 600.0),
        ],
    )
    def test_parse(self, raw: str, expected: float) -> None:
        assert parse_race_time(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_means_no_result(self, raw) -> None:
        assert parse_race_time(raw) is None

    @pytest.mark.parametrize("raw", ["abc", "1:75,00", "12:34:56", "-5"])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            parse_race_time(raw)

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(125.30, "2:05,30"), (83.45, "1:23,45"), (59.99, "0:59,99"), (600.0, "10:00,00")],
    )
    def test_format(self, seconds: float, expected: str) -> None:
        assert format_race_time(seconds) == expected

    def test_format_none(self) -> None:
        assert format_race_time(None) == "—"

    def test_roundtrip(self) -> None:
        for value in (60.0, 61.5, 83.45, 125.30, 240.99):
            assert parse_race_time(format_race_time(value)) == pytest.approx(value)


class TestPlace:
    def test_format(self) -> None:
        assert format_place(1) == "1-е место"
        assert format_place(12) == "12-е место"
        assert format_place(None) == "—"


class TestPlural:
    def test_forms(self) -> None:
        assert plural_ru(1, "лошадь", "лошади", "лошадей") == "1 лошадь"
        assert plural_ru(3, "лошадь", "лошади", "лошадей") == "3 лошади"
        assert plural_ru(5, "лошадь", "лошади", "лошадей") == "5 лошадей"
        assert plural_ru(11, "лошадь", "лошади", "лошадей") == "11 лошадей"
        assert plural_ru(21, "лошадь", "лошади", "лошадей") == "21 лошадь"


class TestParsers:
    def test_parse_positive_int_range(self) -> None:
        assert parse_positive_int("12", field="Возраст", maximum=39) == 12
        with pytest.raises(ValidationError):
            parse_positive_int("0", field="Возраст")
        with pytest.raises(ValidationError):
            parse_positive_int("40", field="Возраст", maximum=39)
        with pytest.raises(ValidationError):
            parse_positive_int("abc", field="Возраст")

    def test_parse_date(self) -> None:
        assert parse_date("2026-05-17").isoformat() == "2026-05-17"
        with pytest.raises(ValidationError):
            parse_date("17.05.2026")
        with pytest.raises(ValidationError):
            parse_date("")

    def test_parse_time_of_day(self) -> None:
        assert parse_time_of_day("14:30").strftime("%H:%M") == "14:30"
        with pytest.raises(ValidationError):
            parse_time_of_day("25:00")


class TestSecurity:
    def test_password_is_not_stored_in_plain_text(self) -> None:
        stored = hash_password("secret123")
        assert "secret123" not in stored
        assert stored.startswith("pbkdf2_sha256$")

    def test_verify(self) -> None:
        stored = hash_password("secret123")
        assert verify_password("secret123", stored)
        assert not verify_password("secret124", stored)

    def test_same_password_gives_different_hashes(self) -> None:
        assert hash_password("secret123") != hash_password("secret123")

    def test_verify_broken_hash(self) -> None:
        assert not verify_password("secret123", "мусор")
        assert not verify_password("secret123", None)
        assert not verify_password("secret123", "")

    def test_session_token_is_hashed(self) -> None:
        token = "abcdef"
        assert hash_session_token(token) != token
        assert len(hash_session_token(token)) == 64
