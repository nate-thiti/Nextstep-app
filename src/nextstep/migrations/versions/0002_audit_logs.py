"""Add the MCP audit log (Phase 6).

Revision ID: 0002_audit_logs
Revises: 0001_initial
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_audit_logs"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(length=50), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("work_item_id", sa.String(length=36), nullable=True),
        sa.Column(
            "changed_fields_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index("ix_audit_logs_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_audit_logs_operation", ["operation"], unique=False)
        batch_op.create_index("ix_audit_logs_outcome", ["outcome"], unique=False)
        batch_op.create_index("ix_audit_logs_work_item_id", ["work_item_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_logs_work_item_id")
        batch_op.drop_index("ix_audit_logs_outcome")
        batch_op.drop_index("ix_audit_logs_operation")
        batch_op.drop_index("ix_audit_logs_created_at")
    op.drop_table("audit_logs")
