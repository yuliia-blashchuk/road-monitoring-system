"""HTTP-ендпоінти модуля admin: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])
