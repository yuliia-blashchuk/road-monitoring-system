"""Безпека: хешування паролів (Argon2) і JWT-токени (F-16, QR-11, QR-12).

Пароль ніде не зберігається у відкритому вигляді: у БД лише хеш Argon2id
з випадковою сіллю. Токен доступу підписується секретом із .env (HS256)
і містить id користувача, роль і строк дії.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()  # Argon2id

# Хеш-заглушка: перевіряється, коли користувача не знайдено, щоб час відповіді
# не підказував, чи існує такий email.
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def hash_password(raw: str) -> str:
    return password_hash.hash(raw)


def verify_password(raw: str, hashed: str | None) -> bool:
    if hashed is None:
        password_hash.verify(raw, DUMMY_HASH)
        return False
    return password_hash.verify(raw, hashed)


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """Повертає (токен, строк дії в секундах)."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires = timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    """Перевіряє підпис і строк дії. Помилка - jwt.InvalidTokenError."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
