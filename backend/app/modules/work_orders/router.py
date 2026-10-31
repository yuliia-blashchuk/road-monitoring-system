"""HTTP-ендпоінти модуля work_orders: прийом запиту, перевірка прав."""

from fastapi import APIRouter

router = APIRouter(prefix="/work-orders", tags=["work-orders"])
