"""HTTP-ендпоінти модуля routing: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/routing", tags=["routing"])
