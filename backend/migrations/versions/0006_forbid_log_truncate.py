"""Журнали не можна очистити командою TRUNCATE (KAN-60, QR-13)

Тригер з міграції 0002 спрацьовує на кожен рядок і забороняє UPDATE і DELETE, але
TRUNCATE видаляє всю таблицю одразу, без рядкових тригерів. Тому для audit_log і
status_history додано тригер BEFORE TRUNCATE з тією самою функцією
forbid_log_modification(): журнал можна лише доповнювати.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("audit_log", "status_history")


def upgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION forbid_log_modification();"
        )


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};")
