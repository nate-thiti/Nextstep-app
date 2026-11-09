"""BUG-008: each restored reference needs its own confirmation."""

from __future__ import annotations

import json

from PySide6.QtWidgets import QMessageBox

from nextstep.application.dto import AddReference, CreateWorkItem
from nextstep.desktop.context import RESTORE_MARKER_NAME
from nextstep.desktop.resume_view import ReferencesPanel
from nextstep.domain.enums import ReferenceType


def test_confirming_one_reference_keeps_the_others_pending(qtbot, app_context, monkeypatch) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    first = app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="First",
            target="https://example.com/first",
        )
    )
    second = app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Second",
            target="https://example.com/second",
        )
    )

    marker = app_context.paths.config_dir / RESTORE_MARKER_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"format_version": 1, "reference_ids": [str(first.id), str(second.id)]}),
        encoding="utf-8",
    )

    panel = ReferencesPanel(app_context)
    qtbot.addWidget(panel)
    panel.set_data(item.id, None, [first, second])

    monkeypatch.setattr(
        "nextstep.desktop.resume_view.reference_target_exists", lambda _reference: True
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "nextstep.desktop.resume_view.open_reference",
        lambda reference: opened.append(reference.label) or True,
    )

    answers = iter(
        (
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
    )
    asked: list[str] = []

    def question(_parent, _title, text, *_args, **_kwargs):
        asked.append(text)
        return next(answers)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))

    panel._open(first)
    assert app_context.reference_requires_confirmation(first.id) is False
    assert app_context.reference_requires_confirmation(second.id) is True

    panel._open(second)
    assert app_context.reference_requires_confirmation(second.id) is True

    # The first reference was already confirmed, so it opens without a prompt.
    panel._open(first)

    panel._open(second)
    assert app_context.reference_requires_confirmation(second.id) is False

    assert opened == ["First", "First", "Second"]
    assert len(asked) == 3
    assert "First" in asked[0]
    assert "Second" in asked[1]
    assert "Second" in asked[2]
    assert not marker.exists()
