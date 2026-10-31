"""HTTP-ендпоінти модуля dedup: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/dedup", tags=["dedup"])
