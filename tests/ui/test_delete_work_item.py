"""BUG-005: permanent delete requires typing the work item title."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.desktop.dialogs import DeleteWorkItemDialog
from nextstep.domain.enums import ReferenceType


def test_delete_button_stays_disabled_until_title_matches(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login"))
    dialog = DeleteWorkItemDialog(item)
    qtbot.addWidget(dialog)

    assert not dialog._delete_button.isEnabled()
    assert not dialog._delete_button.isDefault()

    dialog._input.setText("fix login")
    assert not dialog._delete_button.isEnabled()

    dialog._input.setText("Fix login!")
    assert not dialog._delete_button.isEnabled()

    dialog._input.setText("  Fix login  ")
    assert dialog._delete_button.isEnabled()

    dialog._input.setText("")
    assert not dialog._delete_button.isEnabled()


def test_cancel_leaves_the_work_item_untouched(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login"))
    dialog = DeleteWorkItemDialog(item)
    qtbot.addWidget(dialog)

    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert app_context.work_items.get(item.id).title == "Fix login"


def test_confirmed_delete_removes_checkpoints_and_references(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login"))
    app_context.checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="next")
    )
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Issue",
            target="https://example.com/issues/42",
        )
    )

    dialog = DeleteWorkItemDialog(item)
    qtbot.addWidget(dialog)
    dialog._input.setText(item.title)
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted

    app_context.work_items.delete(item.id)

    assert app_context.work_items.list_items() == []
    with app_context.database.uow() as uow:
        assert uow.checkpoints.count() == 0
        assert uow.references.count() == 0
