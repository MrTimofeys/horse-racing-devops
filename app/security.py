"""Пароли и токены сессий.

Требования ТЗ к защите от НСД:
* идентификация пользователя (вход по логину и паролю);
* «слепые» пароли — символы не показываются на экране (реализовано в шаблоне
  через ``<input type="password">``);
* пароли не хранятся в открытом виде.

Для хеширования используется PBKDF2-HMAC-SHA256 из стандартной библиотеки:
это исключает дополнительные зависимости и гарантированно собирается
на любом стенде.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Вернуть строку вида ``pbkdf2_sha256$<итерации>$<соль>$<хеш>``."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Проверить пароль, устойчиво к повреждённым/пустым записям."""
    if not stored:
        return False
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored.split("$")
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    if algorithm != ALGORITHM:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def generate_session_token() -> str:
    """Случайный токен сессии, который уходит в cookie."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """В базе храним только хеш токена: утечка БД не даёт войти под пользователем."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
