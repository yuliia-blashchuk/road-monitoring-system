"""Фільтрація полів за класифікацією даних (табл. 11, 13) - другий рівень перевірки RBAC.

Після перевірки дії й області дії з відповіді вилучаються поля, вищі за рівень ролі:
- публічна карта отримує лише публічні поля;
- водій бачить свою заявку без внутрішніх полів служби;
- диспетчер і поліція отримують псевдонім «Заявник #…» замість author_id;
- підрядник отримує заявку без author_id і comment (БП-5).
"""

import hashlib
import hmac
from typing import Any

from app.core.config import get_settings
from app.core.enums import AccessRole, DataLevel

PUBLIC, INTERNAL, CONFIDENTIAL, PERSONAL = (
    DataLevel.PUBLIC,
    DataLevel.INTERNAL,
    DataLevel.CONFIDENTIAL,
    DataLevel.PERSONAL,
)

# Рівні полів заявки (табл. 13).
REQUEST_FIELDS: dict[str, DataLevel] = {
    "id": PUBLIC,
    "number": PUBLIC,
    "problem_type_id": PUBLIC,
    "location": PUBLIC,
    "address": PUBLIC,
    "status": PUBLIC,
    "confirmations_count": PUBLIC,
    "service_id": PUBLIC,
    "created_at": PUBLIC,
    "priority": INTERNAL,
    "is_suspicious": INTERNAL,
    "is_reopened": INTERNAL,
    "reject_reason": INTERNAL,
    "deadline": INTERNAL,
    "progress_percent": INTERNAL,
    "copy_service_id": INTERNAL,
    "contractor_id": INTERNAL,
    "author_id": PERSONAL,
    "comment": PERSONAL,
}

# Які рівні бачить роль. None - анонімний відвідувач публічної карти.
ROLE_LEVELS: dict[AccessRole | None, frozenset[DataLevel]] = {
    None: frozenset({PUBLIC}),
    AccessRole.DRIVER: frozenset({PUBLIC, PERSONAL}),  # лише для власних заявок (OWN)
    AccessRole.DISPATCHER: frozenset({PUBLIC, INTERNAL, PERSONAL}),
    AccessRole.POLICE: frozenset({PUBLIC, INTERNAL, PERSONAL}),
    AccessRole.CONTRACTOR: frozenset({PUBLIC, INTERNAL}),
    AccessRole.ADMIN: frozenset({PUBLIC, INTERNAL, CONFIDENTIAL, PERSONAL}),
    AccessRole.DATA_GOVERNANCE: frozenset({PUBLIC}),
}

# Ролі, які бачать автора лише під псевдонімом.
PSEUDONYM_ROLES = frozenset({AccessRole.DISPATCHER, AccessRole.POLICE})


def author_pseudonym(author_id: int) -> str:
    """Стабільний псевдонім «Заявник #4821», з якого не можна відновити id без секрету."""
    key = get_settings().jwt_secret.encode()
    digest = hmac.new(key, f"author:{author_id}".encode(), hashlib.sha256).hexdigest()
    return f"Заявник #{int(digest[:8], 16) % 9000 + 1000}"


def filter_request(data: dict[str, Any], role: AccessRole | None) -> dict[str, Any]:
    """Повертає копію заявки лише з полями, дозволеними ролі.

    Невідоме поле вважається персональним - нове поле не «витече» випадково.
    """
    allowed = ROLE_LEVELS.get(role, frozenset({PUBLIC}))
    result = {
        key: value for key, value in data.items() if REQUEST_FIELDS.get(key, PERSONAL) in allowed
    }
    if role in PSEUDONYM_ROLES and "author_id" in result:
        author_id = result.pop("author_id")
        result["author"] = author_pseudonym(author_id) if author_id is not None else None
    return result
