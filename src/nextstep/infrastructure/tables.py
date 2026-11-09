"""SQLAlchemy Core table definitions.

The schema mirrors MVP_SPEC section 9. Migrations must produce the same shape;
integration tests run Alembic against a temporary database to catch drift.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
    text,
)

from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.infrastructure.db import GUID, EnumType, UtcDateTime

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

work_items = Table(
    "work_items",
    metadata,
    Column("id", GUID, primary_key=True),
    Column("title", Text, nullable=False),
    Column("goal", Text, nullable=True),
    Column("status", EnumType(WorkItemStatus), nullable=False, index=True),
    Column("group_name", String(100), nullable=True, index=True),
    Column("created_at", UtcDateTime, nullable=False),
    Column("updated_at", UtcDateTime, nullable=False, index=True),
)

checkpoints = Table(
    "checkpoints",
    metadata,
    Column("id", GUID, primary_key=True),
    Column(
        "work_item_id",
        GUID,
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("completed_work", Text, nullable=True),
    Column("stopped_at", Text, nullable=False),
    Column("blockers", Text, nullable=True),
    Column("next_actions", Text, nullable=False),
    Column("context_summary", Text, nullable=True),
    Column("status_after_save", EnumType(WorkItemStatus), nullable=False),
    Column("created_at", UtcDateTime, nullable=False, index=True),
    Column("updated_at", UtcDateTime, nullable=False),
)

work_references = Table(
    "work_references",
    metadata,
    Column("id", GUID, primary_key=True),
    Column(
        "work_item_id",
        GUID,
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "checkpoint_id",
        GUID,
        ForeignKey("checkpoints.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    ),
    Column("type", EnumType(ReferenceType), nullable=False),
    Column("label", String(200), nullable=False),
    Column("target", Text, nullable=False),
    Column(
        "metadata_json",
        JSON,
        nullable=False,
        server_default=text("'{}'"),
    ),
    Column("created_at", UtcDateTime, nullable=False),
    Column("updated_at", UtcDateTime, nullable=False),
)

app_settings = Table(
    "app_settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value_json", JSON, nullable=False),
    Column("updated_at", UtcDateTime, nullable=False),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", GUID, primary_key=True),
    Column("created_at", UtcDateTime, nullable=False, index=True),
    Column("actor", String(50), nullable=False),
    Column("tool_name", String(100), nullable=False),
    Column("operation", String(50), nullable=False, index=True),
    Column("outcome", String(20), nullable=False, index=True),
    Column("work_item_id", GUID, nullable=True, index=True),
    Column("changed_fields_json", JSON, nullable=False, server_default=text("'[]'")),
    Column("error_code", String(50), nullable=True),
)

# Explicit composite index for the common "latest checkpoint" query.
Index(
    "ix_checkpoints_work_item_created",
    checkpoints.c.work_item_id,
    checkpoints.c.created_at,
)
