"""Command DTOs validated at the application-service boundary.

Pydantic checks shape and types. Domain length/trim rules are applied inside
the services so every caller (UI, CLI, future MCP) gets identical behaviour.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from nextstep.domain.enums import ReferenceType, WorkItemStatus


class Command(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CreateWorkItem(Command):
    title: str
    goal: str | None = None
    group_name: str | None = None
    status: WorkItemStatus = WorkItemStatus.ACTIVE


class UpdateWorkItem(Command):
    """Partial update; only fields explicitly provided are changed."""

    title: str | None = None
    goal: str | None = None
    group_name: str | None = None


class SaveCheckpoint(Command):
    work_item_id: UUID
    stopped_at: str
    next_actions: str
    completed_work: str | None = None
    blockers: str | None = None
    context_summary: str | None = None


class UpdateCheckpoint(Command):
    """Partial edit of an existing checkpoint.

    Editing a checkpoint never changes the Work Item status retroactively.
    """

    stopped_at: str | None = None
    next_actions: str | None = None
    completed_work: str | None = None
    blockers: str | None = None
    context_summary: str | None = None


class AddReference(Command):
    work_item_id: UUID
    type: ReferenceType
    label: str
    target: str
    checkpoint_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class UpdateReference(Command):
    label: str | None = None
    target: str | None = None
    metadata: dict[str, Any] | None = None
