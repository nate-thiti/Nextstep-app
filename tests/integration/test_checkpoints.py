from __future__ import annotations

import pytest

from nextstep.application.checkpoints import CheckpointService
from nextstep.application.dto import CreateWorkItem, SaveCheckpoint, UpdateCheckpoint
from nextstep.application.work_items import WorkItemService
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import NotFoundError, ValidationError
from nextstep.infrastructure.repositories import SqlAlchemyCheckpointRepository


def test_save_requires_stopped_at_and_next_actions(
    work_items: WorkItemService, checkpoints: CheckpointService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    with pytest.raises(ValidationError) as error:
        checkpoints.save(SaveCheckpoint(work_item_id=item.id, stopped_at="  ", next_actions="next"))
    assert error.value.field == "stopped_at"

    with pytest.raises(ValidationError) as error:
        checkpoints.save(SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="  "))
    assert error.value.field == "next_actions"


def test_save_keeps_work_item_status_and_updates_timestamp(
    work_items: WorkItemService, checkpoints: CheckpointService, clock
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    work_items.change_status(item.id, WorkItemStatus.PAUSED)
    clock.advance(minutes=5)

    checkpoint = checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="middleware fixed",
            next_actions="run integration tests",
        )
    )

    refreshed = work_items.get(item.id)
    assert refreshed.status is WorkItemStatus.PAUSED
    assert refreshed.updated_at == checkpoint.created_at


def test_save_defaults_to_current_status(
    work_items: WorkItemService, checkpoints: CheckpointService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    work_items.change_status(item.id, WorkItemStatus.PAUSED)

    checkpoints.save(SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="next"))

    assert work_items.get(item.id).status is WorkItemStatus.PAUSED


def test_save_rejects_progress_for_archived_work(
    work_items: WorkItemService, checkpoints: CheckpointService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    work_items.archive(item.id)

    with pytest.raises(ValidationError) as error:
        checkpoints.save(
            SaveCheckpoint(
                work_item_id=item.id,
                stopped_at="here",
                next_actions="next",
            )
        )
    assert error.value.field == "work_item_id"


def test_save_missing_work_item_raises(checkpoints: CheckpointService) -> None:
    from uuid import uuid4

    with pytest.raises(NotFoundError):
        checkpoints.save(
            SaveCheckpoint(work_item_id=uuid4(), stopped_at="here", next_actions="next")
        )


def test_latest_is_by_created_at_not_updated_at(
    work_items: WorkItemService, checkpoints: CheckpointService, clock
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    first = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="one", next_actions="a")
    )
    clock.advance(minutes=1)
    second = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="two", next_actions="b")
    )
    clock.advance(minutes=1)

    checkpoints.update(first.id, UpdateCheckpoint(stopped_at="one edited"))

    latest = checkpoints.get_latest(item.id)
    assert latest is not None
    assert latest.id == second.id


def test_history_is_newest_first(
    work_items: WorkItemService, checkpoints: CheckpointService, clock
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    first = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="one", next_actions="a")
    )
    clock.advance(minutes=1)
    second = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="two", next_actions="b")
    )

    history = checkpoints.history(item.id)

    assert [checkpoint.id for checkpoint in history] == [second.id, first.id]


def test_update_does_not_change_work_item_status(
    work_items: WorkItemService, checkpoints: CheckpointService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    checkpoint = checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="here",
            next_actions="next",
        )
    )
    work_items.change_status(item.id, WorkItemStatus.ACTIVE)

    checkpoints.update(checkpoint.id, UpdateCheckpoint(blockers="waiting on review"))

    assert work_items.get(item.id).status is WorkItemStatus.ACTIVE
    assert checkpoints.get(checkpoint.id).blockers == "waiting on review"


def test_delete_latest_falls_back_to_previous(
    work_items: WorkItemService, checkpoints: CheckpointService, clock
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    first = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="one", next_actions="a")
    )
    clock.advance(minutes=1)
    second = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="two", next_actions="b")
    )

    checkpoints.delete(second.id)

    latest = checkpoints.get_latest(item.id)
    assert latest is not None
    assert latest.id == first.id


def test_get_latest_returns_none_without_checkpoints(
    work_items: WorkItemService, checkpoints: CheckpointService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    assert checkpoints.get_latest(item.id) is None


def test_save_rolls_back_when_checkpoint_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
    work_items: WorkItemService,
    checkpoints: CheckpointService,
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    def boom(self, checkpoint) -> None:
        raise RuntimeError("insert failed")

    monkeypatch.setattr(SqlAlchemyCheckpointRepository, "add", boom)

    with pytest.raises(RuntimeError):
        checkpoints.save(
            SaveCheckpoint(
                work_item_id=item.id,
                stopped_at="here",
                next_actions="next",
            )
        )

    assert work_items.get(item.id).status is WorkItemStatus.ACTIVE
    assert checkpoints.get_latest(item.id) is None
