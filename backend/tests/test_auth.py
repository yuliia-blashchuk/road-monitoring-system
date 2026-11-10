"""Реєстрація і вхід (KAN-49, F-16)."""

import jwt
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.users.models import User

API = "/api/v1/auth"
DRIVER = {
    "email": "Olena@Example.com",
    "password": "Secret123",
    "full_name": "Олена Коваль",
    "phone": "+380671234567",
    "consents": ["terms", "personal_data", "email_notifications"],
}


async def register(client: AsyncClient, **override) -> dict:
    response = await client.post(f"{API}/register", json={**DRIVER, **override})
    assert response.status_code == 201, response.text
    return response.json()


async def login(client: AsyncClient, email: str, password: str):
    return await client.post(f"{API}/login", data={"username": email, "password": password})


async def actions(db: AsyncSession) -> list[str]:
    return list((await db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all())


async def test_register_creates_driver_with_consents(client: AsyncClient) -> None:
    body = await register(client)
    assert body["email"] == "olena@example.com"  # email зберігається в нижньому регістрі
    assert body["role"] == "driver"
    assert {c["type"] for c in body["consents"]} == {
        "terms",
        "personal_data",
        "email_notifications",
    }
    assert "password" not in body and "password_hash" not in body


async def test_password_stored_as_argon2_hash(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    stored = await db.scalar(select(User.password_hash))
    assert stored.startswith("$argon2id$")
    assert DRIVER["password"] not in stored


async def test_register_without_required_consent_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/register", json={**DRIVER, "consents": ["terms", "email_notifications"]}
    )
    assert response.status_code == 422
    assert "personal_data" in response.text


async def test_register_duplicate_email_conflict(client: AsyncClient) -> None:
    await register(client)
    response = await client.post(f"{API}/register", json={**DRIVER, "email": "OLENA@example.com"})
    assert response.status_code == 409


async def test_weak_password_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{API}/register", json={**DRIVER, "password": "onlyletters"})
    assert response.status_code == 422


async def test_consents_written_to_audit(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    assert (await actions(db)).count("CONSENT_GRANTED") == 3


async def test_login_returns_jwt_with_role(client: AsyncClient) -> None:
    user = await register(client)
    response = await login(client, "OLENA@example.com", DRIVER["password"])
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["role"] == "driver"
    s = get_settings()
    claims = jwt.decode(body["access_token"], s.jwt_secret, algorithms=[s.jwt_algorithm])
    assert claims["sub"] == str(user["id"]) and claims["role"] == "driver"


async def test_login_wrong_password_401_and_audit(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    response = await login(client, DRIVER["email"], "Wrong12345")
    assert response.status_code == 401
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "LOGIN_FAILED"))
    assert entry.result == "denied"
    assert entry.new_value["email"] == "o***@example.com"  # email маскується
    assert entry.correlation_id is not None


async def test_login_unknown_email_same_answer(client: AsyncClient) -> None:
    response = await login(client, "nobody@example.com", "Secret123")
    assert response.status_code == 401
    assert response.json()["detail"] == "Невірний email або пароль"


async def test_login_success_audited_and_last_login(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    await login(client, DRIVER["email"], DRIVER["password"])
    assert "LOGIN_SUCCESS" in await actions(db)
    assert await db.scalar(select(User.last_login_at)) is not None


async def test_inactive_user_cannot_login(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    await db.execute(text("UPDATE users SET is_active = false"))
    await db.commit()
    response = await login(client, DRIVER["email"], DRIVER["password"])
    assert response.status_code == 403


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/me")).status_code == 401
    bad = await client.get(f"{API}/me", headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401


async def test_me_with_token(client: AsyncClient) -> None:
    await register(client)
    token = (await login(client, DRIVER["email"], DRIVER["password"])).json()["access_token"]
    response = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["full_name"] == DRIVER["full_name"]


async def test_audit_never_contains_password(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    await login(client, DRIVER["email"], "Wrong12345")
    dump = " ".join(str(r) for r in (await db.execute(text("SELECT * FROM audit_log"))).all())
    assert "Secret123" not in dump and "Wrong12345" not in dump


async def test_response_has_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert len(response.headers["X-Request-ID"]) == 36
