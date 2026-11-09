from __future__ import annotations

from pathlib import Path

import pytest

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint, UpdateReference
from nextstep.application.references import ReferenceService
from nextstep.application.work_items import WorkItemService
from nextstep.domain.enums import ReferenceType
from nextstep.domain.errors import NotFoundError, ValidationError
from nextstep.infrastructure.db import Database


def test_add_reference_types(
    work_items: WorkItemService, references: ReferenceService, tmp_path: Path
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    repo = tmp_path / "repo"
    repo.mkdir()

    file_ref = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.FILE,
            label="session.py",
            target=str(repo / "session.py"),
        )
    )
    url_ref = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Docs",
            target="https://example.com/auth",
        )
    )
    git_ref = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.GIT_REPOSITORY,
            label="Repo",
            target=str(repo),
            metadata={"branch": "main", "commit": "abc123"},
        )
    )

    assert file_ref.type is ReferenceType.FILE
    assert url_ref.target == "https://example.com/auth"
    assert git_ref.metadata["branch"] == "main"


def test_target_path_is_normalized(
    work_items: WorkItemService, references: ReferenceService, tmp_path: Path
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    messy = str(tmp_path / "repo" / ".." / "repo" / "file.py")

    reference = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.FILE,
            label="File",
            target=messy,
        )
    )

    assert reference.target == str(tmp_path / "repo" / "file.py")


@pytest.mark.parametrize("url", ["ftp://example.com", "javascript:alert(1)", "example.com"])
def test_url_scheme_is_restricted(
    work_items: WorkItemService, references: ReferenceService, url: str
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    with pytest.raises(ValidationError) as error:
        references.add(
            AddReference(work_item_id=item.id, type=ReferenceType.URL, label="Bad", target=url)
        )
    assert error.value.field == "target"


def test_relative_path_is_rejected(
    work_items: WorkItemService, references: ReferenceService
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))

    with pytest.raises(ValidationError):
        references.add(
            AddReference(
                work_item_id=item.id,
                type=ReferenceType.FOLDER,
                label="Relative",
                target="some/relative/path",
            )
        )


def test_checkpoint_reference_must_belong_to_work_item(
    work_items: WorkItemService, checkpoints, references: ReferenceService
) -> None:
    first = work_items.create(CreateWorkItem(title="First"))
    second = work_items.create(CreateWorkItem(title="Second"))
    checkpoint = checkpoints.save(
        SaveCheckpoint(work_item_id=first.id, stopped_at="here", next_actions="next")
    )

    with pytest.raises(ValidationError):
        references.add(
            AddReference(
                work_item_id=second.id,
                checkpoint_id=checkpoint.id,
                type=ReferenceType.URL,
                label="Docs",
                target="https://example.com",
            )
        )


def test_deleting_checkpoint_removes_its_references_only(
    work_items: WorkItemService,
    checkpoints,
    references: ReferenceService,
    database: Database,
) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    checkpoint = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="next")
    )
    item_level = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Item",
            target="https://example.com",
        )
    )
    checkpoint_level = references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=checkpoint.id,
            type=ReferenceType.URL,
            label="Checkpoint",
            target="https://example.org",
        )
    )

    checkpoints.delete(checkpoint.id)

    with pytest.raises(NotFoundError):
        references.get(checkpoint_level.id)
    assert references.get(item_level.id).label == "Item"


def test_update_reference(work_items: WorkItemService, references: ReferenceService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    reference = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Docs",
            target="https://example.com",
        )
    )

    updated = references.update(reference.id, UpdateReference(label="API docs"))

    assert updated.label == "API docs"
    assert updated.target == "https://example.com"


def test_delete_reference(work_items: WorkItemService, references: ReferenceService) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    reference = references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Docs",
            target="https://example.com",
        )
    )

    references.delete(reference.id)

    assert references.list_for_work_item(item.id) == []
