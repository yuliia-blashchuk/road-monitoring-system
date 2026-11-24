"""KAN-113: опис API (/docs, OpenAPI) збігається з реальними ендпоінтами.

Тест звіряє документацію з тим, що API справді відповідає:

- кожен ендпоінт має опис українською і групу (tag);
- кожна помилка в документації має схему тіла відповіді;
- код, який ендпоінт реально повертає анонімові й користувачам усіх ролей,
  є в документації (не буває «прихованих» 401/403/404/409);
- ендпоінти, згадані в README, існують саме з такими методами.

Звіт: docs/api/KAN-113-api-check.md.
"""

import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.main import app
from app.modules.users.models import User
from tests.factories import auth, make_contractor, make_driver, make_staff

PREFIX = get_settings().api_prefix
README = Path(__file__).resolve().parents[2] / "README.md"
WEST = "Комунальна служба Залізничного району (демо)"
POLICE = "Дорожня поліція (демо)"
CYRILLIC = re.compile("[А-Яа-яІіЇїЄєҐґ]")

# Помилки, які ендпоінт повертає за певних даних. Пробні запити їх не викликають,
# тому перевіряємо, що вони описані в документації (код - (метод, шлях)).
KNOWN_ERRORS = {
    ("post", "/auth/register"): {"409"},
    ("post", "/auth/login"): {"401"},
    ("delete", "/consents/me/{consent_type}"): {"409"},
    ("post", "/reports"): {"403", "429"},
    ("post", "/reports/{request_id}/confirm"): {"404", "409"},
    ("patch", "/reports/{request_id}/status"): {"404", "409"},
    ("post", "/work-orders"): {"404", "409"},
    ("post", "/work-orders/{request_id}/progress"): {"404", "409"},
    ("post", "/notifications/{notification_id}/read"): {"404"},
    ("post", "/admin/problem-types"): {"409"},
}


def operations() -> list[tuple[str, str, dict]]:
    spec = app.openapi()
    return [
        (method, path.removeprefix(PREFIX), operation)
        for path, ops in spec["paths"].items()
        for method, operation in ops.items()
    ]


def probe_url(path: str) -> str:
    """Неіснуючі id, щоб пробні запити нічого не змінили в даних."""
    url = path.replace("{consent_type}", "contact")
    return PREFIX + re.sub(r"\{[^}]+\}", "999999", url)


async def make_users(db: AsyncSession) -> dict[str, User | None]:
    return {
        "анонім": None,
        "водій": await make_driver(db),
        "диспетчер": await make_staff(db, "dispatcher", service_name=WEST),
        "поліція": await make_staff(db, "dispatcher", service_name=POLICE),
        "підрядник": await make_contractor(db),
        "адміністратор": await make_staff(db, "admin"),
        "Data Governance": await make_staff(db, "data_governance"),
    }


def test_every_operation_described() -> None:
    """TC-DOC-01: опис українською, група й хоча б одна успішна відповідь."""
    problems = []
    for method, path, operation in operations():
        if not CYRILLIC.search(operation.get("summary", "")):
            problems.append(f"{method.upper()} {path}: немає опису українською")
        if not operation.get("tags"):
            problems.append(f"{method.upper()} {path}: немає групи (tag)")
        if not any(code.startswith("2") for code in operation["responses"]):
            problems.append(f"{method.upper()} {path}: немає успішної відповіді")
    assert problems == []


def test_errors_have_body_schema() -> None:
    """TC-DOC-02: кожна помилка 4xx у документації має схему тіла відповіді."""
    missing = [
        f"{method.upper()} {path} {code}"
        for method, path, operation in operations()
        for code, response in operation["responses"].items()
        if code.startswith("4")
        and "schema" not in response.get("content", {}).get("application/json", {})
    ]
    assert missing == []


def test_known_errors_documented() -> None:
    """TC-DOC-03: помилки бізнес-правил (конфлікти, ліміт, не знайдено) описані."""
    documented = {(method, path): set(op["responses"]) for method, path, op in operations()}
    missing = {
        key: sorted(codes - documented[key])
        for key, codes in KNOWN_ERRORS.items()
        if codes - documented[key]
    }
    assert missing == {}


async def test_real_status_codes_documented(client: AsyncClient, db: AsyncSession) -> None:
    """TC-DOC-04: усі коди, які ендпоінти реально повертають різним ролям, описані."""
    users = await make_users(db)
    undocumented = []
    for method, path, operation in operations():
        documented = set(operation["responses"])
        for role, user in users.items():
            response = await client.request(
                method.upper(), probe_url(path), headers=auth(user) if user else {}
            )
            if str(response.status_code) not in documented:
                undocumented.append(f"{method.upper()} {path} [{role}] -> {response.status_code}")
    assert undocumented == []


def readme_endpoints() -> set[tuple[str, str]]:
    found = re.findall(r"(GET|POST|PUT|PATCH|DELETE) +`?(/api/v1/[\w/{}.-]+)", README.read_text())
    return {(method.lower(), re.sub(r"\{[^}]+\}", "{}", path)) for method, path in found}


@pytest.mark.skipif(not README.exists(), reason="README поза репозиторієм")
def test_readme_endpoints_exist() -> None:
    """TC-DOC-05: ендпоінти, згадані в README, існують з тим самим методом."""
    real = {(m, re.sub(r"\{[^}]+\}", "{}", PREFIX + p)) for m, p, _ in operations()}
    assert readme_endpoints() - real == set()
