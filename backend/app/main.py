"""Точка входу: створює застосунок FastAPI і підключає модулі."""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.modules.admin.router import router as admin_router
from app.modules.audit.router import router as audit_router
from app.modules.dedup.router import router as dedup_router
from app.modules.notifications.router import router as notifications_router
from app.modules.reports.router import router as reports_router
from app.modules.routing.router import router as routing_router
from app.modules.users.router import router as users_router
from app.modules.work_orders.router import router as work_orders_router

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix=settings.api_prefix)


@api.get("/health", tags=["system"])
async def health() -> dict:
    """Перевірка, що API живий."""
    return {"status": "ok"}


@api.get("/health/db", tags=["system"])
async def health_db(session: AsyncSession = Depends(get_session)) -> dict:
    """Перевірка, що API бачить базу даних і PostGIS."""
    postgis = (await session.execute(text("SELECT postgis_version()"))).scalar_one()
    return {"status": "ok", "postgis": postgis}


for module_router in (
    users_router,
    reports_router,
    routing_router,
    dedup_router,
    work_orders_router,
    notifications_router,
    audit_router,
    admin_router,
):
    api.include_router(module_router)

app.include_router(api)
