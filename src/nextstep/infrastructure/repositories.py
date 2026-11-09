"""SQLAlchemy repository implementations.

Queries are built from Core table columns rather than mapped class attributes.
The domain classes stay plain dataclasses, so static type checkers see their
declared field types instead of SQLAlchemy instrumented attributes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.orm import Session

from nextstep.domain.entities import AuditLogEntry, Checkpoint, WorkItem, WorkReference
from nextstep.domain.enums import AuditOutcome, McpOperation, WorkItemStatus
from nextstep.infrastructure.tables import (
    app_settings,
    audit_logs,
    checkpoints,
    work_items,
    work_references,
)

_LIKE_ESCAPE = "\\"


def _like_pattern(search: str) -> str:
    """Build a ``%term%`` pattern that treats user input literally."""
    escaped = (
        search.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


class SqlAlchemyWorkItemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, work_item: WorkItem) -> None:
        self._session.add(work_item)

    def get(self, work_item_id: UUID) -> WorkItem | None:
        return self._session.get(WorkItem, work_item_id)

    def get_many(self, work_item_ids: list[UUID]) -> dict[UUID, WorkItem]:
        if not work_item_ids:
            return {}
        statement = select(WorkItem).where(work_items.c.id.in_(work_item_ids))
        return {item.id: item for item in self._session.scalars(statement)}

    def list_items(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        statement = self._filtered(
            select(WorkItem),
            status=status,
            group_name=group_name,
            search=search,
            work_item_ids=work_item_ids,
        )
        statement = (
            statement.order_by(work_items.c.updated_at.desc(), work_items.c.title.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement))

    def count_items(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
    ) -> int:
        """Count every matching item, not just the loaded page."""
        statement = self._filtered(
            select(func.count()).select_from(work_items),
            status=status,
            group_name=group_name,
            search=search,
            work_item_ids=work_item_ids,
        )
        return int(self._session.execute(statement).scalar_one())

    @staticmethod
    def _filtered(
        statement: Any,
        *,
        status: WorkItemStatus | None,
        group_name: str | None,
        search: str | None,
        work_item_ids: list[UUID] | None = None,
    ) -> Any:
        if status is not None:
            statement = statement.where(work_items.c.status == status.value)
        if group_name is not None:
            statement = statement.where(work_items.c.group_name == group_name)
        if work_item_ids is not None:
            statement = statement.where(work_items.c.id.in_(work_item_ids))
        if search and search.strip():
            statement = statement.where(SqlAlchemyWorkItemRepository._search_clause(search.strip()))
        return statement

    def list_all(self) -> list[WorkItem]:
        statement = select(WorkItem).order_by(work_items.c.created_at.asc(), work_items.c.id.asc())
        return list(self._session.scalars(statement))

    def count(self) -> int:
        statement = select(func.count()).select_from(work_items)
        return int(self._session.execute(statement).scalar_one())

    @staticmethod
    def _search_clause(search: str) -> Any:
        """Case-insensitive LIKE across work items, checkpoints and references.

        FTS5 replaces this in Phase 3; the user-facing behaviour stays the same.
        """
        pattern = _like_pattern(search)

        checkpoint_match = (
            select(checkpoints.c.id)
            .where(
                checkpoints.c.work_item_id == work_items.c.id,
                or_(
                    checkpoints.c.completed_work.like(pattern, escape=_LIKE_ESCAPE),
                    checkpoints.c.stopped_at.like(pattern, escape=_LIKE_ESCAPE),
                    checkpoints.c.blockers.like(pattern, escape=_LIKE_ESCAPE),
                    checkpoints.c.next_actions.like(pattern, escape=_LIKE_ESCAPE),
                    checkpoints.c.context_summary.like(pattern, escape=_LIKE_ESCAPE),
                ),
            )
            .exists()
        )
        reference_match = (
            select(work_references.c.id)
            .where(
                work_references.c.work_item_id == work_items.c.id,
                or_(
                    work_references.c.label.like(pattern, escape=_LIKE_ESCAPE),
                    work_references.c.target.like(pattern, escape=_LIKE_ESCAPE),
                ),
            )
            .exists()
        )

        return or_(
            work_items.c.title.like(pattern, escape=_LIKE_ESCAPE),
            work_items.c.goal.like(pattern, escape=_LIKE_ESCAPE),
            work_items.c.group_name.like(pattern, escape=_LIKE_ESCAPE),
            checkpoint_match,
            reference_match,
        )

    def delete(self, work_item: WorkItem) -> None:
        self._session.delete(work_item)

    def list_groups(self) -> list[str]:
        statement = (
            select(work_items.c.group_name).where(work_items.c.group_name.is_not(None)).distinct()
        )
        names = [name for name in self._session.scalars(statement) if name is not None]
        return sorted(names, key=str.casefold)

    def rename_group(self, old_name: str, new_name: str) -> int:
        statement = (
            update(work_items)
            .where(work_items.c.group_name == old_name)
            .values(group_name=new_name)
            .execution_options(synchronize_session=False)
        )
        result = self._session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    def clear_group(self, name: str) -> int:
        statement = (
            update(work_items)
            .where(work_items.c.group_name == name)
            .values(group_name=None)
            .execution_options(synchronize_session=False)
        )
        result = self._session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)


class SqlAlchemyCheckpointRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, checkpoint: Checkpoint) -> None:
        self._session.add(checkpoint)

    def get(self, checkpoint_id: UUID) -> Checkpoint | None:
        return self._session.get(Checkpoint, checkpoint_id)

    def latest_for(self, work_item_id: UUID) -> Checkpoint | None:
        statement = (
            select(Checkpoint)
            .where(checkpoints.c.work_item_id == work_item_id)
            .order_by(checkpoints.c.created_at.desc(), checkpoints.c.id.desc())
            .limit(1)
        )
        return self._session.scalars(statement).first()

    def latest_for_many(self, work_item_ids: list[UUID]) -> dict[UUID, Checkpoint]:
        if not work_item_ids:
            return {}

        rank = (
            func.row_number()
            .over(
                partition_by=checkpoints.c.work_item_id,
                order_by=(checkpoints.c.created_at.desc(), checkpoints.c.id.desc()),
            )
            .label("rank")
        )
        ranked = (
            select(checkpoints.c.id.label("checkpoint_id"), rank)
            .where(checkpoints.c.work_item_id.in_(work_item_ids))
            .subquery()
        )
        statement = select(Checkpoint).where(
            checkpoints.c.id.in_(select(ranked.c.checkpoint_id).where(ranked.c.rank == 1))
        )
        return {
            checkpoint.work_item_id: checkpoint for checkpoint in self._session.scalars(statement)
        }

    def list_for(
        self, work_item_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Checkpoint]:
        statement = (
            select(Checkpoint)
            .where(checkpoints.c.work_item_id == work_item_id)
            .order_by(checkpoints.c.created_at.desc(), checkpoints.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement))

    def search(
        self,
        query: str,
        *,
        work_item_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Checkpoint]:
        statement = select(Checkpoint).where(self._search_clause(query, work_item_ids))
        statement = (
            statement.order_by(checkpoints.c.created_at.desc(), checkpoints.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement))

    def count_search(
        self,
        query: str,
        *,
        work_item_ids: list[UUID] | None = None,
    ) -> int:
        statement = select(func.count()).select_from(checkpoints)
        statement = statement.where(self._search_clause(query, work_item_ids))
        return int(self._session.execute(statement).scalar_one())

    @staticmethod
    def _search_clause(query: str, work_item_ids: list[UUID] | None) -> Any:
        pattern = _like_pattern(query)
        clause = or_(
            checkpoints.c.completed_work.like(pattern, escape=_LIKE_ESCAPE),
            checkpoints.c.stopped_at.like(pattern, escape=_LIKE_ESCAPE),
            checkpoints.c.blockers.like(pattern, escape=_LIKE_ESCAPE),
            checkpoints.c.next_actions.like(pattern, escape=_LIKE_ESCAPE),
            checkpoints.c.context_summary.like(pattern, escape=_LIKE_ESCAPE),
        )
        if work_item_ids is None:
            return clause
        return clause & checkpoints.c.work_item_id.in_(work_item_ids)

    def list_all(self) -> list[Checkpoint]:
        statement = select(Checkpoint).order_by(
            checkpoints.c.created_at.asc(), checkpoints.c.id.asc()
        )
        return list(self._session.scalars(statement))

    def count(self) -> int:
        statement = select(func.count()).select_from(checkpoints)
        return int(self._session.execute(statement).scalar_one())

    def delete(self, checkpoint: Checkpoint) -> None:
        self._session.delete(checkpoint)


class SqlAlchemyReferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, reference: WorkReference) -> None:
        self._session.add(reference)

    def get(self, reference_id: UUID) -> WorkReference | None:
        return self._session.get(WorkReference, reference_id)

    def list_for_work_item(self, work_item_id: UUID) -> list[WorkReference]:
        statement = (
            select(WorkReference)
            .where(work_references.c.work_item_id == work_item_id)
            .order_by(
                work_references.c.created_at.asc(),
                work_references.c.label.asc(),
            )
        )
        return list(self._session.scalars(statement))

    def list_for_checkpoint(self, checkpoint_id: UUID) -> list[WorkReference]:
        statement = (
            select(WorkReference)
            .where(work_references.c.checkpoint_id == checkpoint_id)
            .order_by(
                work_references.c.created_at.asc(),
                work_references.c.label.asc(),
            )
        )
        return list(self._session.scalars(statement))

    def list_for_resume(
        self, work_item_id: UUID, checkpoint_id: UUID | None
    ) -> list[WorkReference]:
        """Work-item references plus references of the latest checkpoint."""
        conditions: list[Any] = [work_references.c.checkpoint_id.is_(None)]
        if checkpoint_id is not None:
            conditions.append(work_references.c.checkpoint_id == checkpoint_id)

        statement = (
            select(WorkReference)
            .where(
                work_references.c.work_item_id == work_item_id,
                or_(*conditions),
            )
            .order_by(
                work_references.c.checkpoint_id.is_not(None).asc(),
                work_references.c.created_at.asc(),
                work_references.c.label.asc(),
            )
        )
        return list(self._session.scalars(statement))

    def list_all(self) -> list[WorkReference]:
        statement = select(WorkReference).order_by(
            work_references.c.created_at.asc(), work_references.c.id.asc()
        )
        return list(self._session.scalars(statement))

    def count(self) -> int:
        statement = select(func.count()).select_from(work_references)
        return int(self._session.execute(statement).scalar_one())

    def delete(self, reference: WorkReference) -> None:
        self._session.delete(reference)


class SqlAlchemySettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> Any | None:
        statement = select(app_settings.c.value_json).where(app_settings.c.key == key)
        return self._session.execute(statement).scalar_one_or_none()

    def set(self, key: str, value: Any) -> None:
        now = datetime.now(UTC)
        exists = self._session.execute(
            select(app_settings.c.key).where(app_settings.c.key == key)
        ).first()
        if exists is None:
            self._session.execute(
                insert(app_settings).values(key=key, value_json=value, updated_at=now)
            )
        else:
            self._session.execute(
                update(app_settings)
                .where(app_settings.c.key == key)
                .values(value_json=value, updated_at=now)
            )


class SqlAlchemyAuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: AuditLogEntry) -> None:
        self._session.execute(
            insert(audit_logs).values(
                id=entry.id,
                created_at=entry.created_at,
                actor=entry.actor,
                tool_name=entry.tool_name,
                operation=entry.operation.value,
                outcome=entry.outcome.value,
                work_item_id=entry.work_item_id,
                changed_fields_json=list(entry.changed_fields),
                error_code=entry.error_code,
            )
        )

    def list_recent(self, limit: int = 50) -> list[AuditLogEntry]:
        statement = (
            select(audit_logs)
            .order_by(audit_logs.c.created_at.desc(), audit_logs.c.id.desc())
            .limit(limit)
        )
        rows = self._session.execute(statement).all()
        return [self._to_entry(row) for row in rows]

    def count(self) -> int:
        statement = select(func.count()).select_from(audit_logs)
        return int(self._session.execute(statement).scalar_one())

    @staticmethod
    def _to_entry(row: Any) -> AuditLogEntry:
        changed = row.changed_fields_json
        return AuditLogEntry(
            id=row.id,
            created_at=row.created_at,
            actor=row.actor,
            tool_name=row.tool_name,
            operation=McpOperation(row.operation),
            outcome=AuditOutcome(row.outcome),
            work_item_id=row.work_item_id,
            changed_fields=(
                tuple(str(value) for value in changed) if isinstance(changed, list) else ()
            ),
            error_code=row.error_code,
        )
