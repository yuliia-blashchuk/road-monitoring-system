"""Сервіс AccessControl: перевірка прав на кожному запиті до API (F-17, QR-10, п. 3.4).

Як працює:
1. Користувач визначається за JWT-токеном (401, якщо токена немає або він недійсний).
2. Роль користувача зводиться до ролі політики (AccessRole): operator і dispatcher -
   «Диспетчер», працівник служби з Service.kind = police - «Поліція».
3. Шукається політика AccessPolicy для (роль, ресурс, дія). Немає політики - доступ
   заборонено (заборонено за замовчуванням): відповідь 403 і запис ACCESS_DENIED в AuditLog.
4. Ендпоінт отримує AccessContext з областю дії (OWN / SERVICE / ALL / PUBLIC) і через
   ensure_target() перевіряє, що конкретний запис входить в цю область.

Використання в ендпоінті:

    AuditView = Annotated[AccessContext, Depends(require("audit", "view"))]

    @router.get("/audit")
    async def list_audit(ctx: AuditView): ...
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.enums import AccessRole, AccessScope, RoleCode, ServiceKind
from app.modules.admin.models import AccessPolicy
from app.modules.audit import service as audit
from app.modules.users.dependencies import CurrentUser, SessionDep
from app.modules.users.models import User

FORBIDDEN = "Недостатньо прав для цієї дії"


def access_role(user: User) -> AccessRole:
    """Роль, за якою шукаються політики (стовпці матриці табл. 14)."""
    code = user.role.code
    if code in (RoleCode.OPERATOR, RoleCode.DISPATCHER):
        if user.service is not None and user.service.kind == ServiceKind.POLICE:
            return AccessRole.POLICE
        return AccessRole.DISPATCHER
    return AccessRole(code)


async def get_policy(
    session: AsyncSession, role: AccessRole, resource: str, action: str
) -> AccessPolicy | None:
    return await session.scalar(
        select(AccessPolicy).where(
            AccessPolicy.role == role.value,
            AccessPolicy.resource == resource,
            AccessPolicy.action == action,
        )
    )


async def list_permissions(session: AsyncSession, role: AccessRole) -> list[AccessPolicy]:
    rows = await session.scalars(
        select(AccessPolicy)
        .where(AccessPolicy.role == role.value)
        .order_by(AccessPolicy.resource, AccessPolicy.action)
    )
    return list(rows)


async def deny(
    user: User | None,
    role: AccessRole | None,
    resource: str,
    action: str,
    endpoint: str,
    reason: str,
    entity_id: int | None = None,
) -> HTTPException:
    """Пише ACCESS_DENIED в окремій транзакції (запит буде скасовано) і повертає 403."""
    async with SessionLocal() as session:
        audit.record(
            session,
            "ACCESS_DENIED",
            actor_id=user.id if user else None,
            actor_role=role.value if role else None,
            entity_type=resource,
            entity_id=entity_id,
            result="denied",
            new_value={"action": action, "endpoint": endpoint, "reason": reason},
        )
        await session.commit()
    return HTTPException(status.HTTP_403_FORBIDDEN, FORBIDDEN)


@dataclass(frozen=True)
class AccessContext:
    """Результат перевірки: хто, яка роль, яка область дії для ресурсу й дії."""

    user: User
    role: AccessRole
    resource: str
    action: str
    scope: AccessScope
    log_access: bool
    endpoint: str

    def can_access(
        self,
        *,
        owner_id: int | None = None,
        service_ids: Iterable[int | None] = (),
        contractor_id: int | None = None,
    ) -> bool:
        """Чи входить конкретний запис в область дії.

        owner_id - автор запису (водій); service_ids - служба й служба-копія заявки;
        contractor_id - підрядник, якому призначено роботи.
        """
        match self.scope:
            case AccessScope.ALL | AccessScope.PUBLIC:
                return True
            case AccessScope.SERVICE:
                return self.user.service_id is not None and self.user.service_id in set(service_ids)
            case AccessScope.OWN:
                if self.role == AccessRole.CONTRACTOR:
                    return (
                        self.user.contractor_id is not None
                        and contractor_id == self.user.contractor_id
                    )
                return owner_id is not None and owner_id == self.user.id
        return False

    async def ensure_target(
        self,
        *,
        entity_id: int | None = None,
        owner_id: int | None = None,
        service_ids: Iterable[int | None] = (),
        contractor_id: int | None = None,
    ) -> None:
        """403 + ACCESS_DENIED, якщо запис поза областю дії (чужа заявка, інша служба)."""
        if not self.can_access(
            owner_id=owner_id, service_ids=service_ids, contractor_id=contractor_id
        ):
            raise await deny(
                self.user,
                self.role,
                self.resource,
                self.action,
                self.endpoint,
                reason=f"out_of_scope:{self.scope.value}",
                entity_id=entity_id,
            )


def require(resource: str, action: str) -> Callable[..., Awaitable[AccessContext]]:
    """Залежність FastAPI: дозволяє запит, лише якщо для ролі є політика (resource, action)."""

    async def dependency(request: Request, user: CurrentUser, session: SessionDep) -> AccessContext:
        role = access_role(user)
        endpoint = f"{request.method} {request.url.path}"
        policy = await get_policy(session, role, resource, action)
        if policy is None:
            raise await deny(user, role, resource, action, endpoint, reason="no_policy")
        return AccessContext(
            user=user,
            role=role,
            resource=resource,
            action=action,
            scope=policy.scope,
            log_access=policy.log_access,
            endpoint=endpoint,
        )

    dependency.__name__ = f"require_{resource}_{action}"
    return dependency
