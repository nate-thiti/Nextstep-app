"""Initial schema for NextStep Phase 1.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_work_items"),
    )
    with op.batch_alter_table("work_items", schema=None) as batch_op:
        batch_op.create_index("ix_work_items_group_name", ["group_name"], unique=False)
        batch_op.create_index("ix_work_items_status", ["status"], unique=False)
        batch_op.create_index("ix_work_items_updated_at", ["updated_at"], unique=False)

    op.create_table(
        "checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_item_id", sa.String(length=36), nullable=False),
        sa.Column("completed_work", sa.Text(), nullable=True),
        sa.Column("stopped_at", sa.Text(), nullable=False),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("next_actions", sa.Text(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("status_after_save", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["work_items.id"],
            name="fk_checkpoints_work_item_id_work_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_checkpoints"),
    )
    with op.batch_alter_table("checkpoints", schema=None) as batch_op:
        batch_op.create_index("ix_checkpoints_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_checkpoints_work_item_id", ["work_item_id"], unique=False)
        batch_op.create_index(
            "ix_checkpoints_work_item_created",
            ["work_item_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "work_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_item_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["checkpoints.id"],
            name="fk_work_references_checkpoint_id_checkpoints",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["work_items.id"],
            name="fk_work_references_work_item_id_work_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_work_references"),
    )
    with op.batch_alter_table("work_references", schema=None) as batch_op:
        batch_op.create_index("ix_work_references_checkpoint_id", ["checkpoint_id"], unique=False)
        batch_op.create_index("ix_work_references_work_item_id", ["work_item_id"], unique=False)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")

    with op.batch_alter_table("work_references", schema=None) as batch_op:
        batch_op.drop_index("ix_work_references_work_item_id")
        batch_op.drop_index("ix_work_references_checkpoint_id")
    op.drop_table("work_references")

    with op.batch_alter_table("checkpoints", schema=None) as batch_op:
        batch_op.drop_index("ix_checkpoints_work_item_created")
        batch_op.drop_index("ix_checkpoints_work_item_id")
        batch_op.drop_index("ix_checkpoints_created_at")
    op.drop_table("checkpoints")

    with op.batch_alter_table("work_items", schema=None) as batch_op:
        batch_op.drop_index("ix_work_items_updated_at")
        batch_op.drop_index("ix_work_items_status")
        batch_op.drop_index("ix_work_items_group_name")
    op.drop_table("work_items")
