"""Resume projection used by Work Detail (MVP_SPEC section 6.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from nextstep.application.ports import UnitOfWork
from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.domain.errors import NotFoundError


@dataclass(frozen=True)
class ResumeData:
    """Everything Work Detail needs in one read."""

    work_item: WorkItem
    latest_checkpoint: Checkpoint | None
    recent_checkpoints: list[Checkpoint]
    references: list[WorkReference]


class ResumeService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def get(self, work_item_id: UUID) -> ResumeData:
        with self._uow_factory() as uow:
            work_item = uow.work_items.get(work_item_id)
            if work_item is None:
                raise NotFoundError("Work item", work_item_id)

            latest = uow.checkpoints.latest_for(work_item_id)
            recent = uow.checkpoints.list_for(work_item_id, limit=5, offset=0)
            references = uow.references.list_for_resume(
                work_item_id, latest.id if latest is not None else None
            )

            return ResumeData(
                work_item=work_item,
                latest_checkpoint=latest,
                recent_checkpoints=recent,
                references=references,
            )
