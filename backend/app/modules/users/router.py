"""HTTP-ендпоінти модуля users: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
