"""Політики доступу для зміни статусу й перегляду історії статусів (KAN-59)

- report.change_status для підрядника (scope own): він ставить «В роботі» і «Виконана»
  лише у призначених йому заявках (табл. 18: «Служба, підрядник (обмежено)»);
  які саме переходи дозволені кожній ролі, визначає modules/reports/lifecycle.py;
- report.view_history: таймлайн статусів бачать автор (own), служба (service),
  призначений підрядник (own) і адміністратор (all) - UC-03, табл. 18.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (role, resource, action, scope)
POLICIES = [
    ("contractor", "report", "change_status", "own"),
    ("driver", "report", "view_history", "own"),
    ("dispatcher", "report", "view_history", "service"),
    ("police", "report", "view_history", "service"),
    ("contractor", "report", "view_history", "own"),
    ("admin", "report", "view_history", "all"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for role, resource, action, scope in POLICIES:
        conn.execute(
            sa.text(
                "INSERT INTO access_policy (role, resource, action, scope, log_access) "
                "VALUES (:role, :resource, :action, CAST(:scope AS access_scope), false)"
            ),
            {"role": role, "resource": resource, "action": action, "scope": scope},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for role, resource, action, _ in POLICIES:
        conn.execute(
            sa.text(
                "DELETE FROM access_policy "
                "WHERE role = :role AND resource = :resource AND action = :action"
            ),
            {"role": role, "resource": resource, "action": action},
        )
