"""HTTP-ендпоінти модуля notifications."""

from fastapi import APIRouter

from app.modules.notifications import service  # noqa: F401  - підписка на події

router = APIRouter(prefix="/notifications", tags=["notifications"])