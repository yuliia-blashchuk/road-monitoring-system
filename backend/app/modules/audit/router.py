"""HTTP-ендпоінти модуля audit: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])
