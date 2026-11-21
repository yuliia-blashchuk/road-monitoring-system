"""Правила маршрутизації за задачею KAN-58 і районні зони служб

- ДТП (аварія) -> дорожня поліція, пріоритет критичний, копія комунальній службі району
  (UC-01 A3, TC-UC01-12: заявку бачать і поліція, і комунальна служба);
- перешкода -> дорожня поліція + копія комунальній службі району, пріоритет високий;
- яма, пошкоджене покриття, світлофор, інше -> комунальна служба свого району.

Для перевірки вибору служби за геозоною (F-23, TC-UC01-13) місто поділено на дві
демонстраційні зони: Залізничний район (захід) і Шевченківський район (схід). Межі -
наближені прямокутники; реальні межі районів адміністратор може завантажити окремо.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_COMMUNAL = "Комунальна дорожня служба (демо)"
WEST = "Комунальна служба Залізничного району (демо)"
EAST = "Комунальна служба Шевченківського району (демо)"
POLICE = "Дорожня поліція (демо)"

CITY = "MULTIPOLYGON(((23.92 49.76, 24.14 49.76, 24.14 49.90, 23.92 49.90, 23.92 49.76)))"
WEST_ZONE = "MULTIPOLYGON(((23.92 49.76, 24.03 49.76, 24.03 49.90, 23.92 49.90, 23.92 49.76)))"
EAST_ZONE = "MULTIPOLYGON(((24.03 49.76, 24.14 49.76, 24.14 49.90, 24.03 49.90, 24.03 49.76)))"

DISTRICTS = (WEST, EAST)

# тип проблеми, служба (None - комунальна служба кожного району), копія, пріоритет
RULES = [
    ("pothole", None, None, "medium"),
    ("damaged_surface", None, None, "low"),
    ("traffic_light", None, None, "high"),
    ("other", None, None, "low"),
    ("accident", POLICE, WEST, "critical"),
    ("obstacle", POLICE, WEST, "high"),
]

# Правила з міграції 0003 - для відкату.
OLD_RULES = [
    ("pothole", OLD_COMMUNAL, None, "medium"),
    ("damaged_surface", OLD_COMMUNAL, None, "low"),
    ("accident", POLICE, OLD_COMMUNAL, "high"),
    ("obstacle", OLD_COMMUNAL, POLICE, "high"),
    ("traffic_light", OLD_COMMUNAL, None, "high"),
    ("other", OLD_COMMUNAL, None, "low"),
]

INSERT_RULE = sa.text(
    "INSERT INTO routing_rule (problem_type_id, service_id, copy_service_id, initial_priority) "
    "SELECT pt.id, s.id, cs.id, CAST(:priority AS priority) "
    "FROM problem_type pt "
    "JOIN service s ON s.name = :service "
    "LEFT JOIN service cs ON cs.name = :copy_service "
    "WHERE pt.code = :code"
)


def _insert_rules(conn, rules) -> None:
    for code, service, copy_service, priority in rules:
        targets = DISTRICTS if service is None else (service,)
        for target in targets:
            conn.execute(
                INSERT_RULE,
                {
                    "code": code,
                    "service": target,
                    "copy_service": copy_service,
                    "priority": priority,
                },
            )


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE service SET name = :west, zone = ST_GeomFromText(:zone, 4326), "
            "contact_email = 'zaliznychnyi@roadmap.local' WHERE name = :old"
        ),
        {"west": WEST, "zone": WEST_ZONE, "old": OLD_COMMUNAL},
    )
    conn.execute(
        sa.text(
            "INSERT INTO service (name, kind, zone, contact_email) "
            "VALUES (:name, 'communal', ST_GeomFromText(:zone, 4326), :email)"
        ),
        {"name": EAST, "zone": EAST_ZONE, "email": "shevchenkivskyi@roadmap.local"},
    )
    conn.execute(sa.text("DELETE FROM routing_rule"))
    _insert_rules(conn, RULES)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM routing_rule"))
    conn.execute(sa.text("DELETE FROM service WHERE name = :east"), {"east": EAST})
    conn.execute(
        sa.text(
            "UPDATE service SET name = :old, zone = ST_GeomFromText(:zone, 4326), "
            "contact_email = 'roads@roadmap.local' WHERE name = :west"
        ),
        {"old": OLD_COMMUNAL, "zone": CITY, "west": WEST},
    )
    _insert_rules(conn, OLD_RULES)
