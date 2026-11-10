"""Бізнес-логіка автентифікації: реєстрація водія, вхід, профіль (F-16, UC-01 «вхід»)."""

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import RoleCode
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.audit import service as audit
from app.modules.users import repository as repo
from app.modules.users.models import User
from app.modules.users.schemas import ConsentOut, RegisterRequest, TokenOut, UserOut

INVALID_CREDENTIALS = "Невірний email або пароль"


async def register_driver(session: AsyncSession, data: RegisterRequest) -> User:
    """Створює акаунт водія і записи згоди. DQ-07: email унікальний."""
    if await repo.get_by_email(session, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Користувач з таким email уже існує")

    role = await repo.get_role(session, RoleCode.DRIVER)
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role_id=role.id,
    )
    try:
        await repo.add_user(session, user)
    except IntegrityError as exc:  # одночасна реєстрація з тим самим email
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Користувач з таким email уже існує") from exc

    version = get_settings().consent_version
    for consent in await repo.add_consents(session, user, data.consents, version):
        audit.record(
            session,
            "CONSENT_GRANTED",
            actor_id=user.id,
            actor_role=role.code,
            entity_type="consent",
            entity_id=consent.id,
            new_value={"type": consent.type.value, "version": version},
        )
    await session.commit()
    await session.refresh(user)
    return user


async def login(session: AsyncSession, email: str, password: str) -> TokenOut:
    """Перевіряє пароль і видає JWT. Кожна спроба пишеться в AuditLog."""
    user = await repo.get_by_email(session, email)
    if not verify_password(password, user.password_hash if user else None):
        audit.record(
            session,
            "LOGIN_FAILED",
            actor_id=user.id if user else None,
            result="denied",
            new_value={"email": audit.mask_email(email.lower()), "reason": "bad_credentials"},
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        audit.record(
            session,
            "LOGIN_FAILED",
            actor_id=user.id,
            actor_role=user.role.code,
            result="denied",
            new_value={"reason": "inactive"},
        )
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Акаунт деактивовано")

    repo.touch_last_login(user)
    audit.record(session, "LOGIN_SUCCESS", actor_id=user.id, actor_role=user.role.code)
    await session.commit()

    token, expires_in = create_access_token(user.id, user.role.code)
    return TokenOut(access_token=token, expires_in=expires_in, role=user.role.code)


async def profile(session: AsyncSession, user: User) -> UserOut:
    consents = await repo.active_consents(session, user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role.code,
        service_id=user.service_id,
        contractor_id=user.contractor_id,
        consents=[ConsentOut.model_validate(c) for c in consents],
    )
