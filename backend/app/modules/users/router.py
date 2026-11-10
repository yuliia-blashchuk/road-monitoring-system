"""HTTP-ендпоінти модуля users: реєстрація, вхід, поточний користувач."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.modules.users import service
from app.modules.users.dependencies import CurrentUser, SessionDep
from app.modules.users.schemas import RegisterRequest, TokenOut, UserOut

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
