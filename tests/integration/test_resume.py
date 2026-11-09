from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.application.resume import ResumeService
from nextstep.domain.enums import ReferenceType
from nextstep.domain.errors import NotFoundError


def test_resume_without_checkpoint(work_items, references, database, clock) -> None:
    service = ResumeService(database.uow)
    item = work_items.create(CreateWorkItem(title="Task", goal="Ship auth"))
    references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Docs",
            target="https://example.com",
        )
    )

    data = service.get(item.id)

    assert data.work_item.title == "Task"
    assert data.latest_checkpoint is None
    assert data.recent_checkpoints == []
    assert [reference.label for reference in data.references] == ["Docs"]


def test_resume_uses_only_latest_checkpoint_references(
    work_items, checkpoints, references, database, clock
) -> None:
    service = ResumeService(database.uow)
    item = work_items.create(CreateWorkItem(title="Task"))

    item_level = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Repo",
            target="https://example.com/repo",
        )
    )
    first = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="one", next_actions="a")
    )
    old_reference = references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=first.id,
            type=ReferenceType.URL,
            label="Old",
            target="https://example.com/old",
        )
    )
    clock.advance(minutes=1)
    second = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="two", next_actions="b")
    )
    latest_reference = references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=second.id,
            type=ReferenceType.URL,
            label="Latest",
            target="https://example.com/latest",
        )
    )

    data = service.get(item.id)

    labels = [reference.label for reference in data.references]
    assert [checkpoint.id for checkpoint in data.recent_checkpoints] == [second.id, first.id]
    assert labels == ["Repo", "Latest"]
    assert item_level.id in {reference.id for reference in data.references}
    assert latest_reference.id in {reference.id for reference in data.references}
    assert old_reference.id not in {reference.id for reference in data.references}


def test_resume_falls_back_after_deleting_latest_checkpoint(
    work_items, checkpoints, references, database
) -> None:
    service = ResumeService(database.uow)
    item = work_items.create(CreateWorkItem(title="Task"))
    first = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="one", next_actions="a")
    )
    references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=first.id,
            type=ReferenceType.URL,
            label="First docs",
            target="https://example.com/one",
        )
    )
    second = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="two", next_actions="b")
    )

    checkpoints.delete(second.id)
    data = service.get(item.id)

    assert data.latest_checkpoint is not None
    assert data.latest_checkpoint.id == first.id
    assert [reference.label for reference in data.references] == ["First docs"]


def test_resume_returns_five_most_recent_progress_updates(
    work_items, checkpoints, database, clock
) -> None:
    service = ResumeService(database.uow)
    item = work_items.create(CreateWorkItem(title="Task"))
    created = []
    for index in range(6):
        created.append(
            checkpoints.save(
                SaveCheckpoint(
                    work_item_id=item.id,
                    stopped_at=f"step {index}",
                    next_actions=f"next {index}",
                )
            )
        )
        clock.advance(minutes=1)

    data = service.get(item.id)

    assert [checkpoint.id for checkpoint in data.recent_checkpoints] == [
        checkpoint.id for checkpoint in reversed(created[1:])
    ]


def test_resume_missing_work_item(database) -> None:
    service = ResumeService(database.uow)

    with pytest.raises(NotFoundError):
        service.get(uuid4())
