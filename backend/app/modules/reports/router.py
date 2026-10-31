"""HTTP-ендпоінти модуля reports: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["reports"])
