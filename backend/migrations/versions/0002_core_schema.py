"""Схема БД за ER-моделлю (KAN-48)

Таблиці моделі даних (п. 4.5) з доповненнями з п. 3.4-3.8: access_policy, city_boundary,
типи згоди, Request.closed_at, User.last_login_at, Photo.storage_key_public,
AuditLog.actor_role / result / correlation_id. Журнали audit_log і status_history
захищені тригером від UPDATE і DELETE (QR-13).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography, Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("audit_log", "status_history")
ENUM_TYPES = (
    "access_scope",
    "service_kind",
    "priority",
    "consent_type",
    "request_status",
    "photo_kind",
)


def upgrade() -> None:
    op.create_table(
        "access_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("resource", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "scope", sa.Enum("own", "service", "all", "public", name="access_scope"), nullable=False
        ),
        sa.Column("log_access", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_policy")),
        sa.UniqueConstraint(
            "role", "resource", "action", name="uq_access_policy_role_resource_action"
        ),
    )
    op.create_geospatial_table(
        "city_boundary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_city_boundary")),
        sa.UniqueConstraint("name", name=op.f("uq_city_boundary_name")),
    )
    op.create_geospatial_index(
        "idx_city_boundary_geom",
        "city_boundary",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_table(
        "contractor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("edrpou", sa.String(length=8), nullable=False),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("edrpou ~ '^[0-9]{8}$'", name=op.f("ck_contractor_edrpou_8_digits")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contractor")),
        sa.UniqueConstraint("edrpou", name=op.f("uq_contractor_edrpou")),
    )
    op.create_table(
        "problem_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_problem_type_color_hex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem_type")),
        sa.UniqueConstraint("code", name=op.f("uq_problem_type_code")),
    )
    op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
        sa.UniqueConstraint("code", name=op.f("uq_role_code")),
    )
    op.create_geospatial_table(
        "service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("kind", sa.Enum("communal", "police", name="service_kind"), nullable=False),
        sa.Column(
            "zone",
            Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service")),
    )
    op.create_geospatial_index(
        "idx_service_zone",
        "service",
        ["zone"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_table(
        "routing_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("problem_type_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("copy_service_id", sa.Integer(), nullable=True),
        sa.Column(
            "initial_priority",
            sa.Enum("low", "medium", "high", "critical", name="priority"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["copy_service_id"],
            ["service.id"],
            name=op.f("fk_routing_rule_copy_service_id_service"),
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_type.id"],
            name=op.f("fk_routing_rule_problem_type_id_problem_type"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["service.id"], name=op.f("fk_routing_rule_service_id_service")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routing_rule")),
        sa.UniqueConstraint("problem_type_id", "service_id", name="uq_routing_rule_type_service"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("contractor_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractor.id"], name=op.f("fk_users_contractor_id_contractor")
        ),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name=op.f("fk_users_role_id_role")),
        sa.ForeignKeyConstraint(
            ["service_id"], ["service.id"], name=op.f("fk_users_service_id_service")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_contractor_id"), "users", ["contractor_id"], unique=False)
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"], unique=False)
    op.create_index(op.f("ix_users_service_id"), "users", ["service_id"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("result", sa.String(length=10), server_default="success", nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_log_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_index(
        op.f("ix_audit_log_correlation_id"), "audit_log", ["correlation_id"], unique=False
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_table(
        "consent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "terms",
                "personal_data",
                "media_sharing",
                "contact",
                "email_notifications",
                name="consent_type",
            ),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_consent_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent")),
    )
    op.create_index("ix_consent_user_id_type", "consent", ["user_id", "type"], unique=False)
    op.create_geospatial_table(
        "request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), sa.Identity(always=False, start=1001), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("problem_type_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("copy_service_id", sa.Integer(), nullable=True),
        sa.Column("contractor_id", sa.Integer(), nullable=True),
        sa.Column(
            "location",
            Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "accepted",
                "in_progress",
                "done",
                "resolved",
                "rejected",
                name="request_status",
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", "critical", name="priority"),
            server_default="medium",
            nullable=False,
        ),
        sa.Column("confirmations_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_suspicious", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_reopened", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("device_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL",
            name=op.f("ck_request_reject_reason_required"),
        ),
        sa.CheckConstraint("char_length(comment) <= 300", name=op.f("ck_request_comment_max_300")),
        sa.CheckConstraint(
            "confirmations_count >= 0", name=op.f("ck_request_confirmations_non_negative")
        ),
        sa.CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name=op.f("ck_request_progress_0_100"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_request_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractor.id"], name=op.f("fk_request_contractor_id_contractor")
        ),
        sa.ForeignKeyConstraint(
            ["copy_service_id"], ["service.id"], name=op.f("fk_request_copy_service_id_service")
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_type.id"],
            name=op.f("fk_request_problem_type_id_problem_type"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["service.id"], name=op.f("fk_request_service_id_service")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request")),
        sa.UniqueConstraint("number", name=op.f("uq_request_number")),
    )
    op.create_geospatial_index(
        "idx_request_location",
        "request",
        ["location"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_request_author_id"), "request", ["author_id"], unique=False)
    op.create_index(op.f("ix_request_contractor_id"), "request", ["contractor_id"], unique=False)
    op.create_index(
        op.f("ix_request_copy_service_id"), "request", ["copy_service_id"], unique=False
    )
    op.create_index(
        "ix_request_queue", "request", ["service_id", "status", "priority"], unique=False
    )
    op.create_table(
        "confirmation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("still_exists", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["request.id"],
            name=op.f("fk_confirmation_request_id_request"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_confirmation_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confirmation")),
        sa.UniqueConstraint("request_id", "user_id", name="uq_confirmation_request_user"),
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["request.id"],
            name=op.f("fk_notification_request_id_request"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
    )
    op.create_index(
        "ix_notification_user_unread", "notification", ["user_id", "is_read"], unique=False
    )
    op.create_table(
        "photo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Enum("before", "after", "act", name="photo_kind"), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("storage_key_public", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')",
            name=op.f("ck_photo_mime_allowed"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 5242880", name=op.f("ck_photo_size_max_5mb")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["request.id"],
            name=op.f("fk_photo_request_id_request"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_photo_uploaded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo")),
    )
    op.create_index(op.f("ix_photo_request_id"), "photo", ["request_id"], unique=False)
    op.create_table(
        "status_history",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "new",
                "accepted",
                "in_progress",
                "done",
                "resolved",
                "rejected",
                name="request_status",
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "new",
                "accepted",
                "in_progress",
                "done",
                "resolved",
                "rejected",
                name="request_status",
            ),
            nullable=False,
        ),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name=op.f("fk_status_history_changed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["request.id"], name=op.f("fk_status_history_request_id_request")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_history")),
    )
    op.create_index(
        op.f("ix_status_history_request_id"), "status_history", ["request_id"], unique=False
    )

    # Журнали лише доповнюються: UPDATE і DELETE заборонені тригером (QR-13).
    op.execute(
        """
        CREATE FUNCTION forbid_log_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Таблиця % лише для додавання записів', TG_TABLE_NAME
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_log_modification();"
        )


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    op.execute("DROP FUNCTION IF EXISTS forbid_log_modification();")
    op.drop_index(op.f("ix_status_history_request_id"), table_name="status_history")
    op.drop_table("status_history")
    op.drop_index(op.f("ix_photo_request_id"), table_name="photo")
    op.drop_table("photo")
    op.drop_index("ix_notification_user_unread", table_name="notification")
    op.drop_table("notification")
    op.drop_table("confirmation")
    op.drop_index("ix_request_queue", table_name="request")
    op.drop_index(op.f("ix_request_copy_service_id"), table_name="request")
    op.drop_index(op.f("ix_request_contractor_id"), table_name="request")
    op.drop_index(op.f("ix_request_author_id"), table_name="request")
    op.drop_geospatial_index(
        "idx_request_location",
        table_name="request",
        postgresql_using="gist",
        column_name="location",
    )
    op.drop_geospatial_table("request")
    op.drop_index("ix_consent_user_id_type", table_name="consent")
    op.drop_table("consent")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_correlation_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_users_service_id"), table_name="users")
    op.drop_index(op.f("ix_users_role_id"), table_name="users")
    op.drop_index(op.f("ix_users_contractor_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("routing_rule")
    op.drop_geospatial_index(
        "idx_service_zone", table_name="service", postgresql_using="gist", column_name="zone"
    )
    op.drop_geospatial_table("service")
    op.drop_table("role")
    op.drop_table("problem_type")
    op.drop_table("contractor")
    op.drop_geospatial_index(
        "idx_city_boundary_geom",
        table_name="city_boundary",
        postgresql_using="gist",
        column_name="geom",
    )
    op.drop_geospatial_table("city_boundary")
    op.drop_table("access_policy")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
