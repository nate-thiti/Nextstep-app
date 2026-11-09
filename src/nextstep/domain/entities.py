"""Domain entities.

These are plain dataclasses. The persistence layer maps them imperatively so
the domain stays free of SQLAlchemy and of any UI framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from nextstep.domain.enums import AuditOutcome, McpOperation, ReferenceType, WorkItemStatus


@dataclass
class WorkItem:
    """A unit of work the user can leave and resume later."""

    id: UUID
    title: str
    status: WorkItemStatus
    created_at: datetime
    updated_at: datetime
    goal: str | None = None
    group_name: str | None = None

    @property
    def needs_confirmation_to_resume(self) -> bool:
        """Completed and archived items must be confirmed before resuming."""
        return self.status in (WorkItemStatus.COMPLETED, WorkItemStatus.ARCHIVED)


@dataclass
class Checkpoint:
    """A snapshot of context at the moment the user stopped working.

    A checkpoint is immutable history: creating a new one never rewrites the
    previous one. ``created_at`` decides which checkpoint is the latest.
    """

    id: UUID
    work_item_id: UUID
    stopped_at: str
    next_actions: str
    status_after_save: WorkItemStatus
    created_at: datetime
    updated_at: datetime
    completed_work: str | None = None
    blockers: str | None = None
    context_summary: str | None = None

    @property
    def has_blocker(self) -> bool:
        return bool(self.blockers)


@dataclass
class WorkReference:
    """A pointer to a file, folder, URL or Git repository.

    Only the pointer and metadata are stored; NextStep never copies the target.
    """

    id: UUID
    work_item_id: UUID
    type: ReferenceType
    label: str
    target: str
    created_at: datetime
    updated_at: datetime
    checkpoint_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditLogEntry:
    """One MCP write attempt, stored without user content.

    Field names and IDs are enough to investigate activity; checkpoint text,
    goals, titles and reference targets are deliberately excluded.
    """

    id: UUID
    created_at: datetime
    actor: str
    tool_name: str
    operation: McpOperation
    outcome: AuditOutcome
    work_item_id: UUID | None
    changed_fields: tuple[str, ...] = ()
    error_code: str | None = None
