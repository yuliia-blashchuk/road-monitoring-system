"""Початкові дані довідників і політик доступу (KAN-48)

Ролі (табл. 12), типи проблем (UC-01), межа міста, служби, правила маршрутизації
з початковими пріоритетами (F-10, БП-1) та політики доступу за матрицею RBAC (табл. 14).

Межа міста та зони служб - наближений прямокутник навколо Львова для прототипу;
реальну межу з OpenStreetMap адміністратор завантажує окремо.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    ("driver", "Водій"),
    ("operator", "Оператор служби"),
    ("dispatcher", "Диспетчер служби"),
    ("contractor", "Підрядник"),
    ("admin", "Адміністратор"),
    ("data_governance", "Data Governance"),
]

# code, name, icon, color
PROBLEM_TYPES = [
    ("pothole", "Яма", "pothole", "#D32F2F"),
    ("damaged_surface", "Пошкоджене покриття", "road-damage", "#F57C00"),
    ("accident", "Аварія", "car-crash", "#7B1FA2"),
    ("obstacle", "Перешкода на дорозі", "obstacle", "#FBC02D"),
    ("traffic_light", "Несправний світлофор", "traffic-light", "#1976D2"),
    ("other", "Інше", "other", "#616161"),
]

CITY_WKT = "MULTIPOLYGON(((23.92 49.76, 24.14 49.76, 24.14 49.90, 23.92 49.90, 23.92 49.76)))"

# name, kind, contact_email
SERVICES = [
    ("Комунальна дорожня служба (демо)", "communal", "roads@roadmap.local"),
    ("Дорожня поліція (демо)", "police", "police@roadmap.local"),
]
COMMUNAL, POLICE = SERVICES[0][0], SERVICES[1][0]

# problem_type code, service, copy_service, initial_priority
ROUTING_RULES = [
    ("pothole", COMMUNAL, None, "medium"),
    ("damaged_surface", COMMUNAL, None, "low"),
    ("accident", POLICE, COMMUNAL, "high"),
    ("obstacle", COMMUNAL, POLICE, "high"),
    ("traffic_light", COMMUNAL, None, "high"),
    ("other", COMMUNAL, None, "low"),
]

# Матриця доступу (табл. 14): resource, action -> {роль: (scope, log_access)}.
# Ролі політик: driver, dispatcher (operator і dispatcher), police, contractor, admin,
# data_governance. Відсутність ролі = заборона (403 + ACCESS_DENIED).
D, DS, P, C, A, DG = "driver", "dispatcher", "police", "contractor", "admin", "data_governance"
ALL_ROLES = (D, DS, P, C, A, DG)
OWN, SERVICE, ALL, PUBLIC = "own", "service", "all", "public"

MATRIX: dict[tuple[str, str], dict[str, tuple[str, bool]]] = {
    ("map", "view"): {r: (PUBLIC, False) for r in ALL_ROLES},
    ("report", "create"): {D: (OWN, False)},
    ("report", "confirm"): {D: (OWN, False)},
    ("report", "rate"): {D: (OWN, False)},
    ("incident", "create"): {P: (OWN, False)},
    ("report", "view_own"): {D: (OWN, False)},
    ("report", "view_internal"): {
        DS: (SERVICE, False),
        P: (SERVICE, False),
        C: (OWN, False),
        A: (ALL, False),
    },
    ("photo", "view_original"): {
        D: (OWN, False),
        DS: (SERVICE, False),
        P: (SERVICE, False),
        A: (ALL, True),
    },
    ("report", "view_author"): {
        D: (OWN, False),
        DS: (SERVICE, False),
        P: (SERVICE, False),
        A: (ALL, False),
    },
    ("report", "reveal_contact"): {
        D: (OWN, False),
        DS: (SERVICE, True),
        P: (SERVICE, True),
        A: (ALL, True),
    },
    ("report", "change_status"): {DS: (SERVICE, False), P: (SERVICE, False)},
    ("report", "mark_suspicious"): {
        DS: (SERVICE, False),
        P: (SERVICE, False),
        A: (ALL, False),
    },
    ("work", "assign"): {A: (ALL, False)},
    ("work", "update_progress"): {C: (OWN, False)},
    ("work", "view"): {DS: (SERVICE, False), C: (OWN, False), A: (ALL, False)},
    ("reference", "manage"): {A: (ALL, False)},
    ("access_policy", "view"): {A: (ALL, False), DG: (ALL, False)},
    ("access_policy", "manage"): {DG: (ALL, False)},
    ("consent", "manage"): {D: (OWN, False)},
    ("consent", "view"): {DG: (ALL, False)},
    ("audit", "view"): {A: (ALL, False), DG: (ALL, False)},
    ("analytics", "view"): {
        DS: (SERVICE, False),
        P: (SERVICE, False),
        A: (ALL, False),
        DG: (ALL, False),
    },
    ("analytics", "export"): {
        DS: (SERVICE, False),
        P: (SERVICE, False),
        A: (ALL, False),
        DG: (ALL, False),
    },
}


def upgrade() -> None:
    role = sa.table("role", sa.column("code"), sa.column("name"))
    op.bulk_insert(role, [{"code": c, "name": n} for c, n in ROLES])

    problem_type = sa.table(
        "problem_type", sa.column("code"), sa.column("name"), sa.column("icon"), sa.column("color")
    )
    op.bulk_insert(
        problem_type,
        [{"code": c, "name": n, "icon": i, "color": col} for c, n, i, col in PROBLEM_TYPES],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO city_boundary (name, geom) VALUES ('Львів', ST_GeomFromText(:wkt, 4326))"
        ),
        {"wkt": CITY_WKT},
    )
    for name, kind, email in SERVICES:
        conn.execute(
            sa.text(
                "INSERT INTO service (name, kind, zone, contact_email) "
                "VALUES (:name, CAST(:kind AS service_kind), "
                "(SELECT geom FROM city_boundary WHERE name = 'Львів'), :email)"
            ),
            {"name": name, "kind": kind, "email": email},
        )

    for code, service, copy_service, priority in ROUTING_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO routing_rule "
                "(problem_type_id, service_id, copy_service_id, initial_priority) "
                "SELECT pt.id, s.id, cs.id, CAST(:priority AS priority) "
                "FROM problem_type pt "
                "JOIN service s ON s.name = :service "
                "LEFT JOIN service cs ON cs.name = :copy_service "
                "WHERE pt.code = :code"
            ),
            {"code": code, "service": service, "copy_service": copy_service, "priority": priority},
        )

    rows = [
        {"role": r, "resource": res, "action": act, "scope": scope, "log_access": log}
        for (res, act), roles in MATRIX.items()
        for r, (scope, log) in roles.items()
    ]
    # scope - тип enum, тому вставляємо через CAST.
    for row in rows:
        conn.execute(
            sa.text(
                "INSERT INTO access_policy (role, resource, action, scope, log_access) "
                "VALUES (:role, :resource, :action, CAST(:scope AS access_scope), :log_access)"
            ),
            row,
        )


def downgrade() -> None:
    for table in (
        "access_policy",
        "routing_rule",
        "service",
        "city_boundary",
        "problem_type",
        "role",
    ):
        op.execute(f"DELETE FROM {table};")
