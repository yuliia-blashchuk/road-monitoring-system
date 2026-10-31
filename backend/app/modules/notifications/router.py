"""HTTP-ендпоінти модуля notifications: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["notifications"])
