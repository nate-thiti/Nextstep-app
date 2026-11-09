"""BUG-003: reference browse buttons route to the right native picker."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog

from nextstep.application.dto import CreateWorkItem
from nextstep.desktop.dialogs import ReferenceDialog
from nextstep.domain.enums import ReferenceType


def test_browse_uses_the_picker_matching_the_reference_type(
    qtbot, app_context, monkeypatch
) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    dialog = ReferenceDialog(app_context, item.id)
    qtbot.addWidget(dialog)

    calls: list[str] = []

    def choose_folder(*_args: object, **_kwargs: object) -> str:
        calls.append("folder")
        return "C:/chosen/folder"

    def choose_file(*_args: object, **_kwargs: object) -> tuple[str, str]:
        calls.append("file")
        return "C:/chosen/file.txt", ""

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(choose_folder))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(choose_file))

    cases = (
        (ReferenceType.FILE, "file", "C:/chosen/file.txt"),
        (ReferenceType.FOLDER, "folder", "C:/chosen/folder"),
        (ReferenceType.GIT_REPOSITORY, "folder", "C:/chosen/folder"),
    )
    for reference_type, expected_call, expected_target in cases:
        calls.clear()
        dialog._type.setCurrentIndex(dialog._type.findData(reference_type))
        dialog._browse_target()
        assert calls == [expected_call]
        assert dialog._target.text() == expected_target

    # Keep the dialog from prompting about unsaved changes during teardown.
    dialog._dirty = False


def test_url_reference_hides_the_browse_button(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    dialog = ReferenceDialog(app_context, item.id)
    qtbot.addWidget(dialog)

    dialog._type.setCurrentIndex(dialog._type.findData(ReferenceType.URL))
    assert dialog._browse.isHidden()

    dialog._type.setCurrentIndex(dialog._type.findData(ReferenceType.FILE))
    assert not dialog._browse.isHidden()
    dialog._dirty = False
