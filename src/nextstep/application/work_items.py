"""Work Item use cases (MVP_SPEC sections 6.3 and 7.1)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from nextstep.application.clock import utcnow
from nextstep.application.dto import CreateWorkItem, UpdateWorkItem
from nextstep.application.ports import UnitOfWork
from nextstep.domain.entities import Checkpoint, WorkItem
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import ConfirmationRequiredError, NotFoundError, ValidationError
from nextstep.domain.validation import (
    MAX_GOAL_LENGTH,
    MAX_GROUP_LENGTH,
    MAX_TITLE_LENGTH,
    group_key,
    optional_text,
    required_text,
)


@dataclass(frozen=True)
class WorkItemSummary:
    """A Work Item plus its latest checkpoint, for the Work List."""

    work_item: WorkItem
    latest_checkpoint: Checkpoint | None

    @property
    def has_blocker(self) -> bool:
        return self.latest_checkpoint is not None and self.latest_checkpoint.has_blocker


@dataclass(frozen=True)
class WorkItemPage:
    """One page of Work List results plus the total matching count."""

    summaries: list[WorkItemSummary]
    total: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.summaries) < self.total


class WorkItemService:
    """Create, edit, filter and change status of Work Items."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def create(
        self,
        command: CreateWorkItem,
        *,
        work_item_id: UUID | None = None,
    ) -> WorkItem:
        title = required_text(command.title, "title", MAX_TITLE_LENGTH)
        goal = optional_text(command.goal, "goal", MAX_GOAL_LENGTH)
        raw_group = optional_text(command.group_name, "group_name", MAX_GROUP_LENGTH)
        now = self._clock()

        with self._uow_factory() as uow:
            group = self._canonical_group(uow, raw_group)
            work_item = WorkItem(
                id=work_item_id or uuid4(),
                title=title,
                status=command.status,
                created_at=now,
                updated_at=now,
                goal=goal,
                group_name=group,
            )
            uow.work_items.add(work_item)
            uow.commit()

        return work_item

    def get(self, work_item_id: UUID) -> WorkItem:
        with self._uow_factory() as uow:
            return self._require(uow, work_item_id)

    def get_many(self, work_item_ids: list[UUID]) -> dict[UUID, WorkItem]:
        with self._uow_factory() as uow:
            return uow.work_items.get_many(work_item_ids)

    def list_all(self) -> list[WorkItem]:
        with self._uow_factory() as uow:
            return uow.work_items.list_all()

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
        with self._uow_factory() as uow:
            return uow.work_items.list_items(
                status=status,
                group_name=group_name,
                search=search,
                work_item_ids=work_item_ids,
                limit=limit,
                offset=offset,
            )

    def list_summaries(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItemSummary]:
        """List work with each item's latest checkpoint in one unit of work."""
        with self._uow_factory() as uow:
            items = uow.work_items.list_items(
                status=status,
                group_name=group_name,
                search=search,
                work_item_ids=work_item_ids,
                limit=limit,
                offset=offset,
            )
            latest = uow.checkpoints.latest_for_many([item.id for item in items])
            return [
                WorkItemSummary(work_item=item, latest_checkpoint=latest.get(item.id))
                for item in items
            ]

    def page_summaries(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> WorkItemPage:
        """Return one page of summaries plus the total number of matches."""
        with self._uow_factory() as uow:
            total = uow.work_items.count_items(
                status=status,
                group_name=group_name,
                search=search,
                work_item_ids=work_item_ids,
            )
            items = uow.work_items.list_items(
                status=status,
                group_name=group_name,
                search=search,
                work_item_ids=work_item_ids,
                limit=limit,
                offset=offset,
            )
            latest = uow.checkpoints.latest_for_many([item.id for item in items])
            summaries = [
                WorkItemSummary(work_item=item, latest_checkpoint=latest.get(item.id))
                for item in items
            ]
        return WorkItemPage(summaries=summaries, total=total, offset=offset)

    def update(self, work_item_id: UUID, command: UpdateWorkItem) -> WorkItem:
        changes = command.model_dump(exclude_unset=True)

        with self._uow_factory() as uow:
            work_item = self._require(uow, work_item_id)

            if "title" in changes:
                work_item.title = required_text(changes["title"], "title", MAX_TITLE_LENGTH)
            if "goal" in changes:
                work_item.goal = optional_text(changes["goal"], "goal", MAX_GOAL_LENGTH)
            if "group_name" in changes:
                raw_group = optional_text(changes["group_name"], "group_name", MAX_GROUP_LENGTH)
                work_item.group_name = self._canonical_group(uow, raw_group)

            work_item.updated_at = self._clock()
            uow.commit()

        return work_item

    def change_status(self, work_item_id: UUID, status: WorkItemStatus) -> WorkItem:
        with self._uow_factory() as uow:
            work_item = self._require(uow, work_item_id)
            if work_item.status is not status:
                work_item.status = status
                work_item.updated_at = self._clock()
                uow.commit()
        return work_item

    def archive(self, work_item_id: UUID) -> WorkItem:
        return self.change_status(work_item_id, WorkItemStatus.ARCHIVED)

    def resume(self, work_item_id: UUID, *, confirm: bool = False) -> WorkItem:
        """Mark the item active again.

        Resuming a completed or archived item requires explicit confirmation so
        the UI cannot silently reopen finished work.
        """
        with self._uow_factory() as uow:
            work_item = self._require(uow, work_item_id)
            if work_item.needs_confirmation_to_resume and not confirm:
                raise ConfirmationRequiredError(
                    f"Work item is {work_item.status.value}; confirm before resuming"
                )
            if work_item.status is not WorkItemStatus.ACTIVE:
                work_item.status = WorkItemStatus.ACTIVE
                work_item.updated_at = self._clock()
                uow.commit()
        return work_item

    def delete(self, work_item_id: UUID) -> None:
        """Permanently delete the item; checkpoints and references cascade."""
        with self._uow_factory() as uow:
            work_item = self._require(uow, work_item_id)
            uow.work_items.delete(work_item)
            uow.commit()

    def list_groups(self) -> list[str]:
        with self._uow_factory() as uow:
            return uow.work_items.list_groups()

    def rename_group(self, old_name: str, new_name: str) -> int:
        old_value = required_text(old_name, "group_name", MAX_GROUP_LENGTH)
        new_value = required_text(new_name, "group_name", MAX_GROUP_LENGTH)

        with self._uow_factory() as uow:
            groups = uow.work_items.list_groups()
            canonical_old = self._match_group(groups, old_value)
            if canonical_old is None:
                raise NotFoundError("Group", old_name)

            collision = self._match_group(
                [group for group in groups if group != canonical_old], new_value
            )
            if collision is not None:
                raise ValidationError("group_name", "already exists")

            updated = uow.work_items.rename_group(canonical_old, new_value)
            uow.commit()

        return updated

    def delete_group(self, name: str) -> int:
        value = required_text(name, "group_name", MAX_GROUP_LENGTH)

        with self._uow_factory() as uow:
            canonical = self._match_group(uow.work_items.list_groups(), value)
            if canonical is None:
                raise NotFoundError("Group", name)
            cleared = uow.work_items.clear_group(canonical)
            uow.commit()

        return cleared

    @staticmethod
    def _require(uow: UnitOfWork, work_item_id: UUID) -> WorkItem:
        work_item = uow.work_items.get(work_item_id)
        if work_item is None:
            raise NotFoundError("Work item", work_item_id)
        return work_item

    @staticmethod
    def _canonical_group(uow: UnitOfWork, name: str | None) -> str | None:
        """Reuse the existing spelling of a group so names cannot duplicate."""
        if name is None:
            return None
        existing = WorkItemService._match_group(uow.work_items.list_groups(), name)
        return existing if existing is not None else name

    @staticmethod
    def _match_group(groups: list[str], name: str) -> str | None:
        key = group_key(name)
        for group in groups:
            if group_key(group) == key:
                return group
        return None
