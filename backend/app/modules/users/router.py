"""HTTP-ендпоінти модуля users: реєстрація, вхід, поточний користувач."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.access_control import AccessContext, access_role, list_permissions, require
from app.core.enums import ConsentType
from app.modules.admin.schemas import AccessPolicyOut
from app.modules.users import service
from app.modules.users.dependencies import CurrentUser, SessionDep
from app.modules.users.schemas import (
    ConsentStatsOut,
    ConsentStatusOut,
    RegisterRequest,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Реєстрація водія",
    responses={409: {"description": "Email уже зареєстровано"}},
)
async def register(data: RegisterRequest, session: SessionDep) -> UserOut:
    user = await service.register_driver(session, data)
    return await service.profile(session, user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Вхід (email + пароль) → JWT",
    responses={401: {"description": "Невірний email або пароль"}},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> TokenOut:
    """Поле **username** - це email. Відповідь містить токен для заголовка
    `Authorization: Bearer <token>`."""
    return await service.login(session, form.username, form.password)


@router.get("/me", response_model=UserOut, summary="Поточний користувач")
async def me(user: CurrentUser, session: SessionDep) -> UserOut:
    return await service.profile(session, user)


@router.get(
    "/me/permissions",
    response_model=list[AccessPolicyOut],
    summary="Дозволені дії поточного користувача",
)
async def my_permissions(user: CurrentUser, session: SessionDep) -> list:
    """Фронтенд показує лише доступні кнопки. Це зручність, а не захист:
    кожен запит усе одно перевіряється на сервері."""
    return await list_permissions(session, access_role(user))


# ---------- «Мої згоди» (KAN-65, п. 3.5) ----------

consent_router = APIRouter(prefix="/consents", tags=["consents"])

ManageOwnConsents = Annotated[AccessContext, Depends(require("consent", "manage"))]
ViewConsents = Annotated[AccessContext, Depends(require("consent", "view"))]


@consent_router.get("/me", response_model=list[ConsentStatusOut], summary="Мої згоди (водій)")
async def my_consents(ctx: ManageOwnConsents, session: SessionDep) -> list:
    return await service.my_consents(session, ctx.user)


@consent_router.put(
    "/me/{consent_type}",
    response_model=list[ConsentStatusOut],
    summary="Надати згоду (водій)",
)
async def grant_consent(
    consent_type: ConsentType, ctx: ManageOwnConsents, session: SessionDep
) -> list:
    """Створює запис згоди актуальної версії тексту; пишеться CONSENT_GRANTED."""
    return await service.grant_my_consent(session, ctx.user, consent_type)


@consent_router.delete(
    "/me/{consent_type}",
    response_model=list[ConsentStatusOut],
    summary="Відкликати згоду (водій)",
    responses={409: {"description": "Обов'язкову згоду не можна відкликати окремо"}},
)
async def revoke_consent(
    consent_type: ConsentType, ctx: ManageOwnConsents, session: SessionDep
) -> list:
    """Заповнює revoked_at; пишеться CONSENT_REVOKED. Діє на наступні передачі даних."""
    return await service.revoke_my_consent(session, ctx.user, consent_type)


@consent_router.get(
    "/stats",
    response_model=list[ConsentStatsOut],
    summary="Статистика згод (Data Governance)",
)
async def consent_stats(_: ViewConsents, session: SessionDep) -> list:
    return await service.consent_stats(session)
