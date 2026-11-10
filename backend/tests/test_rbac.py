"""RBAC на рівні API (KAN-50, F-17, QR-10): ролі, області дії, 403 + ACCESS_DENIED,
фільтрація полів за класифікацією."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import AccessContext, access_role, get_policy
from app.core.classification import author_pseudonym, filter_request
from app.core.enums import AccessRole, AccessScope, ServiceKind
from app.core.security import create_access_token, hash_password
from app.modules.admin.models import Contractor, Service
from app.modules.audit.models import AuditLog
from app.modules.users import repository as repo
from app.modules.users.models import User

# (роль у таблиці role, вид служби) -> очікувана роль політики
USERS = {
    "driver": ("driver", None),
    "dispatcher": ("dispatcher", ServiceKind.COMMUNAL),
    "operator": ("operator", ServiceKind.COMMUNAL),
    "police": ("dispatcher", ServiceKind.POLICE),
    "contractor": ("contractor", None),
    "admin": ("admin", None),
    "dg": ("data_governance", None),
}


async def make_user(db: AsyncSession, key: str) -> User:
    role_code, kind = USERS[key]
    service = await db.scalar(select(Service).where(Service.kind == kind)) if kind else None
    contractor = None
    if role_code == "contractor":
        contractor = Contractor(name="Тест-підрядник", edrpou="12345678")
        db.add(contractor)
        await db.flush()
    user = User(
        email=f"{key}@test.ua",
        password_hash=hash_password("Secret123"),
        full_name=key,
        role_id=(await repo.get_role(db, role_code)).id,
        service_id=service.id if service else None,
        contractor_id=contractor.id if contractor else None,
    )
    db.add(user)
    await db.commit()
    return await repo.get_by_id(db, user.id)


def auth(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, user.role.code)
    return {"Authorization": f"Bearer {token}"}


# ---------- роль політики ----------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("driver", AccessRole.DRIVER),
        ("dispatcher", AccessRole.DISPATCHER),
        ("operator", AccessRole.DISPATCHER),  # operator і dispatcher - однакові права
        ("police", AccessRole.POLICE),  # працівник служби kind = police
        ("contractor", AccessRole.CONTRACTOR),
        ("admin", AccessRole.ADMIN),
        ("dg", AccessRole.DATA_GOVERNANCE),
    ],
)
async def test_access_role(db: AsyncSession, key: str, expected: AccessRole) -> None:
    assert access_role(await make_user(db, key)) == expected


# ---------- матриця на реальних ендпоінтах ----------

ENDPOINTS = {
    "audit": ("GET", "/api/v1/audit", {"admin", "dg"}),
    "policies": ("GET", "/api/v1/admin/access-policies", {"admin", "dg"}),
    "routing": ("GET", "/api/v1/admin/routing-rules", {"admin"}),
}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("key", USERS)
async def test_endpoint_matrix(
    client: AsyncClient, db: AsyncSession, endpoint: str, key: str
) -> None:
    method, url, allowed = ENDPOINTS[endpoint]
    user = await make_user(db, key)
    response = await client.request(method, url, headers=auth(user))
    assert response.status_code == (200 if key in allowed else 403), response.text


async def test_anonymous_gets_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/audit")).status_code == 401


async def test_public_problem_types_without_login(client: AsyncClient) -> None:
    response = await client.get("/api/v1/problem-types")
    assert response.status_code == 200
    assert {t["code"] for t in response.json()} >= {"pothole", "accident", "obstacle"}


async def test_denied_request_written_to_audit(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    response = await client.get("/api/v1/audit", headers=auth(driver))
    assert response.status_code == 403
    assert response.json()["detail"] == "Недостатньо прав для цієї дії"

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert entry.actor_id == driver.id
    assert entry.actor_role == "driver"
    assert entry.result == "denied"
    assert entry.new_value == {
        "action": "view",
        "endpoint": "GET /api/v1/audit",
        "reason": "no_policy",
    }
    assert str(entry.correlation_id) == response.headers["X-Request-ID"]


async def test_audit_view_is_itself_audited(client: AsyncClient, db: AsyncSession) -> None:
    admin = await make_user(db, "admin")
    await client.get("/api/v1/audit", headers=auth(admin))
    assert await db.scalar(select(AuditLog).where(AuditLog.action == "AUDIT_VIEWED"))


async def test_separation_of_duties(client: AsyncClient, db: AsyncSession) -> None:
    """Адміністратор веде довідники; Data Governance - ні (п. 3.4)."""
    new_type = {"code": "open_manhole", "name": "Відкритий люк", "icon": "m", "color": "#8D6E63"}
    dg = await make_user(db, "dg")
    admin = await make_user(db, "admin")
    url = "/api/v1/admin/problem-types"
    assert (await client.post(url, json=new_type, headers=auth(dg))).status_code == 403
    try:
        assert (await client.post(url, json=new_type, headers=auth(admin))).status_code == 201
    finally:
        await db.execute(text("DELETE FROM problem_type WHERE code = 'open_manhole'"))
        await db.commit()


async def test_routing_rules_show_priorities(client: AsyncClient, db: AsyncSession) -> None:
    admin = await make_user(db, "admin")
    rules = (await client.get("/api/v1/admin/routing-rules", headers=auth(admin))).json()
    obstacle = next(r for r in rules if r["problem_type"] == "obstacle")
    assert obstacle["initial_priority"] == "high" and obstacle["copy_service"] is not None


async def test_my_permissions(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    perms = (await client.get("/api/v1/auth/me/permissions", headers=auth(driver))).json()
    pairs = {(p["resource"], p["action"]) for p in perms}
    assert ("report", "create") in pairs
    assert ("audit", "view") not in pairs


# ---------- політики з матриці табл. 14 ----------


@pytest.mark.parametrize(
    ("role", "resource", "action", "scope"),
    [
        (AccessRole.DRIVER, "report", "create", AccessScope.OWN),
        (AccessRole.POLICE, "incident", "create", AccessScope.OWN),
        (AccessRole.DISPATCHER, "report", "change_status", AccessScope.SERVICE),
        (AccessRole.CONTRACTOR, "work", "update_progress", AccessScope.OWN),
        (AccessRole.ADMIN, "work", "assign", AccessScope.ALL),
        (AccessRole.DATA_GOVERNANCE, "access_policy", "manage", AccessScope.ALL),
    ],
)
async def test_policy_exists(
    db: AsyncSession, role: AccessRole, resource: str, action: str, scope: AccessScope
) -> None:
    policy = await get_policy(db, role, resource, action)
    assert policy is not None and policy.scope == scope


@pytest.mark.parametrize(
    ("role", "resource", "action"),
    [
        (AccessRole.DISPATCHER, "incident", "create"),  # ДТП реєструє лише поліція
        (AccessRole.ADMIN, "report", "change_status"),  # адмін не змінює статуси
        (AccessRole.ADMIN, "access_policy", "manage"),
        (AccessRole.CONTRACTOR, "report", "view_author"),  # БП-5
        (AccessRole.DATA_GOVERNANCE, "report", "view_internal"),
        (AccessRole.DRIVER, "audit", "view"),
    ],
)
async def test_policy_absent_means_denied(
    db: AsyncSession, role: AccessRole, resource: str, action: str
) -> None:
    assert await get_policy(db, role, resource, action) is None


async def test_contact_reveal_is_logged_each_time(db: AsyncSession) -> None:
    """«*» у табл. 14: розкриття контакту автора фіксується окремо."""
    policy = await get_policy(db, AccessRole.DISPATCHER, "report", "reveal_contact")
    assert policy.log_access is True


# ---------- область дії (OWN / SERVICE / ALL) ----------


def ctx(user: User, role: AccessRole, scope: AccessScope) -> AccessContext:
    return AccessContext(user, role, "report", "view_internal", scope, False, "GET /test")


async def test_scope_own_driver(db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    c = ctx(driver, AccessRole.DRIVER, AccessScope.OWN)
    assert c.can_access(owner_id=driver.id)
    assert not c.can_access(owner_id=driver.id + 100)


async def test_scope_service(db: AsyncSession) -> None:
    dispatcher = await make_user(db, "dispatcher")
    c = ctx(dispatcher, AccessRole.DISPATCHER, AccessScope.SERVICE)
    assert c.can_access(service_ids=[dispatcher.service_id])
    assert c.can_access(service_ids=[999, dispatcher.service_id])  # копія заявки
    assert not c.can_access(service_ids=[999])


async def test_scope_own_contractor(db: AsyncSession) -> None:
    contractor = await make_user(db, "contractor")
    c = ctx(contractor, AccessRole.CONTRACTOR, AccessScope.OWN)
    assert c.can_access(contractor_id=contractor.contractor_id)
    assert not c.can_access(contractor_id=None)


async def test_out_of_scope_denied_and_audited(db: AsyncSession) -> None:
    dispatcher = await make_user(db, "dispatcher")
    c = ctx(dispatcher, AccessRole.DISPATCHER, AccessScope.SERVICE)
    with pytest.raises(Exception) as exc:
        await c.ensure_target(entity_id=42, service_ids=[999])
    assert exc.value.status_code == 403
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert entry.entity_id == 42 and entry.new_value["reason"] == "out_of_scope:service"


# ---------- фільтрація полів за класифікацією ----------

REQUEST = {
    "id": 1,
    "number": 1001,
    "status": "new",
    "location": [24.03, 49.84],
    "priority": "high",
    "is_suspicious": False,
    "author_id": 7,
    "comment": "Глибока яма біля зупинки",
}


def test_public_view_only_public_fields() -> None:
    view = filter_request(REQUEST, None)
    assert set(view) == {"id", "number", "status", "location"}


def test_dispatcher_sees_pseudonym_not_author() -> None:
    view = filter_request(REQUEST, AccessRole.DISPATCHER)
    assert "author_id" not in view
    assert view["author"] == author_pseudonym(7)
    assert view["author"].startswith("Заявник #")
    assert view["priority"] == "high"


def test_contractor_no_personal_data() -> None:
    """БП-5: підрядник не бачить автора й коментаря."""
    view = filter_request(REQUEST, AccessRole.CONTRACTOR)
    assert "author_id" not in view and "author" not in view and "comment" not in view
    assert view["priority"] == "high"


def test_driver_sees_own_comment_without_internal_fields() -> None:
    view = filter_request(REQUEST, AccessRole.DRIVER)
    assert view["comment"] and "priority" not in view and "is_suspicious" not in view


def test_admin_sees_all() -> None:
    assert filter_request(REQUEST, AccessRole.ADMIN) == REQUEST


def test_unknown_field_treated_as_personal() -> None:
    view = filter_request({**REQUEST, "new_secret_field": "x"}, AccessRole.CONTRACTOR)
    assert "new_secret_field" not in view
