"""Залежності FastAPI: поточний користувач за JWT-токеном."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import decode_access_token
from app.modules.users import repository as repo
from app.modules.users.models import User

# tokenUrl - адреса входу; завдяки цьому в Swagger з'являється кнопка «Authorize».
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_prefix}/auth/login", auto_error=False
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized(detail: str = "Потрібно увійти в систему") -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    session: SessionDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    if not token:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise _unauthorized("Недійсний або прострочений токен") from exc

    user = await repo.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Недійсний або прострочений токен")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
