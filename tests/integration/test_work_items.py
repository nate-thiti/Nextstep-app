from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.dto import CreateWorkItem, UpdateWorkItem
from nextstep.application.work_items import WorkItemService
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import ConfirmationRequiredError, NotFoundError, ValidationError
from nextstep.infrastructure.db import Database


def test_create_defaults_to_active(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="  Fix login  "))

    assert item.title == "Fix login"
    assert item.status is WorkItemStatus.ACTIVE
    assert item.goal is None
    assert item.group_name is None


def test_create_rejects_blank_title(work_items: WorkItemService) -> None:
    with pytest.raises(ValidationError):
        work_items.create(CreateWorkItem(title="   "))


def test_create_rejects_long_title(work_items: WorkItemService) -> None:
    with pytest.raises(ValidationError):
        work_items.create(CreateWorkItem(title="x" * 201))


def test_get_missing_item_raises(work_items: WorkItemService) -> None:
    with pytest.raises(NotFoundError):
        work_items.get(uuid4())


def test_update_only_changes_given_fields(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Fix login", goal="Ship auth", group_name="Auth"))

    updated = work_items.update(item.id, UpdateWorkItem(title="Fix auth"))

    assert updated.title == "Fix auth"
    assert updated.goal == "Ship auth"
    assert updated.group_name == "Auth"


def test_update_can_clear_optional_fields(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task", goal="Goal"))

    updated = work_items.update(item.id, UpdateWorkItem(goal=None))

    assert updated.goal is None


def test_update_touches_updated_at(work_items: WorkItemService, clock) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    clock.advance(minutes=5)

    updated = work_items.update(item.id, UpdateWorkItem(title="Renamed"))

    assert updated.updated_at > item.created_at


def test_change_status(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    paused = work_items.change_status(item.id, WorkItemStatus.PAUSED)

    assert paused.status is WorkItemStatus.PAUSED


def test_resume_active_item_needs_no_confirmation(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    assert work_items.resume(item.id).status is WorkItemStatus.ACTIVE


def test_resume_completed_item_requires_confirmation(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task", status=WorkItemStatus.COMPLETED))

    with pytest.raises(ConfirmationRequiredError):
        work_items.resume(item.id)

    resumed = work_items.resume(item.id, confirm=True)
    assert resumed.status is WorkItemStatus.ACTIVE


def test_resume_archived_item_requires_confirmation(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    work_items.archive(item.id)

    with pytest.raises(ConfirmationRequiredError):
        work_items.resume(item.id)


def test_archive_keeps_data(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    archived = work_items.archive(item.id)

    assert archived.status is WorkItemStatus.ARCHIVED
    assert work_items.get(item.id).title == "Task"


def test_list_filters_and_orders_by_updated_at(work_items: WorkItemService, clock) -> None:
    first = work_items.create(CreateWorkItem(title="First", group_name="A"))
    clock.advance(minutes=1)
    second = work_items.create(CreateWorkItem(title="Second", group_name="B"))
    clock.advance(minutes=1)
    work_items.update(first.id, UpdateWorkItem(title="First updated"))

    ordered = work_items.list_items()
    assert [item.title for item in ordered] == ["First updated", "Second"]

    assert [item.id for item in work_items.list_items(group_name="B")] == [second.id]
    assert work_items.list_items(status=WorkItemStatus.PAUSED) == []


def test_delete_cascades_checkpoints_and_references(
    work_items: WorkItemService, checkpoints, references, database: Database
) -> None:
    from nextstep.application.dto import AddReference, SaveCheckpoint
    from nextstep.domain.enums import ReferenceType

    item = work_items.create(CreateWorkItem(title="Task"))
    checkpoints.save(SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="next"))
    references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Docs",
            target="https://example.com",
        )
    )

    work_items.delete(item.id)

    with database.engine.connect() as connection:
        checkpoint_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM checkpoints"
        ).scalar_one()
        reference_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM work_references"
        ).scalar_one()

    assert checkpoint_count == 0
    assert reference_count == 0
    with pytest.raises(NotFoundError):
        work_items.get(item.id)


def test_group_names_reuse_existing_spelling(work_items: WorkItemService) -> None:
    work_items.create(CreateWorkItem(title="One", group_name="Work"))

    second = work_items.create(CreateWorkItem(title="Two", group_name="work"))

    assert second.group_name == "Work"
    assert work_items.list_groups() == ["Work"]


def test_rename_group_is_case_insensitive(work_items: WorkItemService) -> None:
    first = work_items.create(CreateWorkItem(title="One", group_name="Work"))
    second = work_items.create(CreateWorkItem(title="Two", group_name="Work"))

    renamed = work_items.rename_group("WORK", "Projects")

    assert renamed == 2
    assert work_items.get(first.id).group_name == "Projects"
    assert work_items.get(second.id).group_name == "Projects"
    assert work_items.list_groups() == ["Projects"]


def test_rename_group_rejects_collision(work_items: WorkItemService) -> None:
    work_items.create(CreateWorkItem(title="One", group_name="Work"))
    work_items.create(CreateWorkItem(title="Two", group_name="Personal"))

    with pytest.raises(ValidationError):
        work_items.rename_group("Work", "personal")


def test_delete_group_clears_items_without_deleting_them(work_items: WorkItemService) -> None:
    item = work_items.create(CreateWorkItem(title="One", group_name="Work"))

    cleared = work_items.delete_group("work")

    assert cleared == 1
    assert work_items.get(item.id).group_name is None
    assert work_items.list_groups() == []
