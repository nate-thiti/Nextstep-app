"""Checkpoint use cases (MVP_SPEC sections 6.4, 6.6 and 7.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from nextstep.application.clock import utcnow
from nextstep.application.dto import SaveCheckpoint, UpdateCheckpoint
from nextstep.application.ports import UnitOfWork
from nextstep.domain.entities import Checkpoint
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import NotFoundError, ValidationError
from nextstep.domain.validation import (
    MAX_CHECKPOINT_TEXT_LENGTH,
    MAX_CONTEXT_SUMMARY_LENGTH,
    MAX_SEARCH_QUERY_LENGTH,
    optional_text,
    required_text,
)


@dataclass(frozen=True)
class CheckpointPage:
    """One page of checkpoint search results plus the total match count."""

    checkpoints: list[Checkpoint]
    total: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.checkpoints) < self.total


class CheckpointService:
    """Record, edit and delete checkpoints.

    A progress update records the Work Item status at that moment but never
    changes it. Lifecycle actions are handled separately by WorkItemService.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def save(self, command: SaveCheckpoint) -> Checkpoint:
        stopped_at = required_text(command.stopped_at, "stopped_at", MAX_CHECKPOINT_TEXT_LENGTH)
        next_actions = required_text(
            command.next_actions, "next_actions", MAX_CHECKPOINT_TEXT_LENGTH
        )
        completed_work = optional_text(
            command.completed_work, "completed_work", MAX_CHECKPOINT_TEXT_LENGTH
        )
        blockers = optional_text(command.blockers, "blockers", MAX_CHECKPOINT_TEXT_LENGTH)
        context_summary = optional_text(
            command.context_summary, "context_summary", MAX_CONTEXT_SUMMARY_LENGTH
        )
        now = self._clock()

        with self._uow_factory() as uow:
            work_item = uow.work_items.get(command.work_item_id)
            if work_item is None:
                raise NotFoundError("Work item", command.work_item_id)
            if work_item.status in (WorkItemStatus.COMPLETED, WorkItemStatus.ARCHIVED):
                raise ValidationError(
                    "work_item_id", "cannot update progress for completed or archived work"
                )

            checkpoint = Checkpoint(
                id=uuid4(),
                work_item_id=work_item.id,
                stopped_at=stopped_at,
                next_actions=next_actions,
                status_after_save=work_item.status,
                created_at=now,
                updated_at=now,
                completed_work=completed_work,
                blockers=blockers,
                context_summary=context_summary,
            )
            uow.checkpoints.add(checkpoint)

            work_item.updated_at = now
            uow.commit()

        return checkpoint

    def get(self, checkpoint_id: UUID) -> Checkpoint:
        with self._uow_factory() as uow:
            return self._require(uow, checkpoint_id)

    def get_latest(self, work_item_id: UUID) -> Checkpoint | None:
        with self._uow_factory() as uow:
            if uow.work_items.get(work_item_id) is None:
                raise NotFoundError("Work item", work_item_id)
            return uow.checkpoints.latest_for(work_item_id)

    def history(self, work_item_id: UUID, *, limit: int = 100, offset: int = 0) -> list[Checkpoint]:
        with self._uow_factory() as uow:
            if uow.work_items.get(work_item_id) is None:
                raise NotFoundError("Work item", work_item_id)
            return uow.checkpoints.list_for(work_item_id, limit=limit, offset=offset)

    def search(
        self,
        query: str,
        *,
        work_item_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CheckpointPage:
        """Search checkpoint text, optionally limited to shared work items."""
        text = required_text(query, "query", MAX_SEARCH_QUERY_LENGTH)
        with self._uow_factory() as uow:
            total = uow.checkpoints.count_search(text, work_item_ids=work_item_ids)
            checkpoints = uow.checkpoints.search(
                text,
                work_item_ids=work_item_ids,
                limit=limit,
                offset=offset,
            )
        return CheckpointPage(checkpoints=checkpoints, total=total, offset=offset)

    def update(self, checkpoint_id: UUID, command: UpdateCheckpoint) -> Checkpoint:
        """Edit checkpoint content only; Work Item status is left untouched."""
        changes = command.model_dump(exclude_unset=True)

        with self._uow_factory() as uow:
            checkpoint = self._require(uow, checkpoint_id)

            if "stopped_at" in changes:
                checkpoint.stopped_at = required_text(
                    changes["stopped_at"], "stopped_at", MAX_CHECKPOINT_TEXT_LENGTH
                )
            if "next_actions" in changes:
                checkpoint.next_actions = required_text(
                    changes["next_actions"], "next_actions", MAX_CHECKPOINT_TEXT_LENGTH
                )
            if "completed_work" in changes:
                checkpoint.completed_work = optional_text(
                    changes["completed_work"], "completed_work", MAX_CHECKPOINT_TEXT_LENGTH
                )
            if "blockers" in changes:
                checkpoint.blockers = optional_text(
                    changes["blockers"], "blockers", MAX_CHECKPOINT_TEXT_LENGTH
                )
            if "context_summary" in changes:
                checkpoint.context_summary = optional_text(
                    changes["context_summary"], "context_summary", MAX_CONTEXT_SUMMARY_LENGTH
                )

            checkpoint.updated_at = self._clock()
            uow.commit()

        return checkpoint

    def delete(self, checkpoint_id: UUID) -> None:
        """Delete a checkpoint; the previous one becomes the latest."""
        with self._uow_factory() as uow:
            checkpoint = self._require(uow, checkpoint_id)
            uow.checkpoints.delete(checkpoint)
            uow.commit()

    @staticmethod
    def _require(uow: UnitOfWork, checkpoint_id: UUID) -> Checkpoint:
        checkpoint = uow.checkpoints.get(checkpoint_id)
        if checkpoint is None:
            raise NotFoundError("Checkpoint", checkpoint_id)
        return checkpoint
