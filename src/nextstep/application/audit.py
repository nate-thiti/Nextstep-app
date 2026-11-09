"""MCP audit log service.

Only metadata is stored: tool, operation, outcome, IDs and changed field names.
Checkpoint text, goals, titles and reference targets never reach this table.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID, uuid4

from nextstep.application.clock import utcnow
from nextstep.application.ports import UnitOfWork
from nextstep.domain.entities import AuditLogEntry
from nextstep.domain.enums import AuditOutcome, McpOperation
from nextstep.domain.errors import ValidationError

ACTOR = "mcp"


class AuditService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def record(
        self,
        *,
        tool_name: str,
        operation: McpOperation,
        outcome: AuditOutcome,
        work_item_id: UUID | None = None,
        changed_fields: Iterable[str] = (),
        error_code: str | None = None,
        entry_id: UUID | None = None,
        actor: str = ACTOR,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=entry_id or uuid4(),
            created_at=self._clock(),
            actor=actor,
            tool_name=tool_name,
            operation=operation,
            outcome=outcome,
            work_item_id=work_item_id,
            changed_fields=tuple(changed_fields),
            error_code=error_code,
        )
        with self._uow_factory() as uow:
            uow.audit_logs.add(entry)
            uow.commit()
        return entry

    def list_recent(self, limit: int = 50) -> list[AuditLogEntry]:
        if limit < 1 or limit > 500:
            raise ValidationError("limit", "must be between 1 and 500")
        with self._uow_factory() as uow:
            return uow.audit_logs.list_recent(limit)

    def count(self) -> int:
        with self._uow_factory() as uow:
            return uow.audit_logs.count()
