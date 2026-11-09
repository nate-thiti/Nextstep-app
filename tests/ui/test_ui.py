"""Headless UI tests for the Phase 2 critical path."""

from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import QApplication, QDialog

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.desktop.dialogs import (
    CheckpointDialog,
    FollowUpDialog,
    QuickCaptureDialog,
    ReferenceDialog,
    WorkEditorDialog,
)
from nextstep.desktop.main_window import CommandPaletteDialog, MainWindow, PaletteEntry
from nextstep.desktop.resume_view import HandoffPreviewDialog, ResumeView
from nextstep.desktop.widgets import StatusBadge
from nextstep.desktop.work_list import WorkListView
from nextstep.domain.enums import ReferenceType, WorkItemStatus


def cell_text(view: WorkListView, row: int, column: int) -> str:
    item = view._table.item(row, column)
    assert item is not None
    return item.text()


def test_work_list_shows_active_items(qtbot, app_context) -> None:
    app_context.work_items.create(CreateWorkItem(title="Fix login"))

    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()

    assert view._table.rowCount() == 1
    assert cell_text(view, 0, 1) == "Fix login"
    assert not view._table.isHidden()
    assert view.view_mode() == "focus"
    assert view._preview_title.text() == "Fix login"
    status_cell = view._table.cellWidget(0, 2)
    assert status_cell is not None
    status_badge = status_cell.findChild(StatusBadge)
    assert status_badge is not None
    assert status_badge.property("status") == "active"
    assert status_badge.minimumWidth() == 96
    status_item = view._table.item(0, 2)
    assert status_item is not None
    assert status_item.text() == ""
    assert status_item.data(Qt.ItemDataRole.UserRole) == "active"
    assert view._table.columnWidth(2) >= 118


def test_work_list_can_switch_to_compact_and_remember_it(qtbot, app_context) -> None:
    app_context.work_items.create(CreateWorkItem(title="Task"))
    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()

    view.set_view_mode("compact")

    assert view.view_mode() == "compact"
    assert view._preview.isHidden()
    assert app_context.settings.get_work_list_view() == "compact"


def test_focus_preview_collapses_when_work_list_is_narrow(qtbot, app_context) -> None:
    app_context.work_items.create(CreateWorkItem(title="Task"))
    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.resize(680, 600)
    view.show()
    qtbot.waitExposed(view)
    view.refresh()

    assert view.view_mode() == "focus"
    assert view._preview.isHidden()

    view.resize(900, 600)
    qtbot.waitUntil(lambda: not view._preview.isHidden())


def test_work_list_empty_state(qtbot, app_context) -> None:
    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()

    assert view._table.rowCount() == 0
    assert view._table.isHidden()
    assert not view._empty.isHidden()


def test_work_list_search_filters_rows(qtbot, app_context) -> None:
    app_context.work_items.create(CreateWorkItem(title="Fix login"))
    app_context.work_items.create(CreateWorkItem(title="Write docs"))

    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view._search.setText("login")
    view.refresh()

    assert view._table.rowCount() == 1
    assert cell_text(view, 0, 1) == "Fix login"


def test_work_list_shows_next_action_and_blocker(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="stuck",
            next_actions="retry the auth test",
            blockers="token expired",
        )
    )

    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()

    assert cell_text(view, 0, 0) == "⚠"
    assert cell_text(view, 0, 4) == "retry the auth test"


def test_resume_view_renders_checkpoint(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login", goal="Ship auth"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="integration test fails",
            next_actions="check cookie after refresh",
            completed_work="middleware fixed",
            blockers="token expired",
        )
    )

    view = ResumeView(app_context)
    qtbot.addWidget(view)
    view.load(item.id)

    assert view._title.text() == "Fix login"
    assert view._next_text.text() == "check cookie after refresh"
    assert view._stopped_text.text() == "integration test fails"
    assert view._completed_text.text() == "middleware fixed"
    assert not view._next_card.isHidden()
    assert not view._blockers_card.isHidden()
    assert view._empty_card.isHidden()
    assert view._timeline.count() == 1
    assert "Next: check cookie after refresh" in view._timeline.item(0).text()


def test_resume_view_without_checkpoint(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))

    view = ResumeView(app_context)
    qtbot.addWidget(view)
    view.load(item.id)

    assert not view._empty_card.isHidden()
    assert view._empty_card.property("role") == "empty"
    assert view._empty_update_button.text() == "Add first update"
    assert view._goal_text.property("role") == "goalText"
    assert view._next_card.isHidden()
    assert view._timeline_card.isHidden()
    assert view._meta.text() == "No progress update yet"
    assert view._save_button.text() == "Update progress"


def test_resume_view_copies_handoff_to_clipboard(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login", goal="Ship auth"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="integration test fails",
            next_actions="check cookie after refresh",
            completed_work="middleware fixed",
        )
    )

    view = ResumeView(app_context)
    qtbot.addWidget(view)
    view.load(item.id)
    assert view._data is not None
    dialog = HandoffPreviewDialog(view._data)
    qtbot.addWidget(dialog)
    dialog._format.setCurrentIndex(1)
    qtbot.mouseClick(dialog._copy, Qt.MouseButton.LeftButton)

    clipboard_text = QApplication.clipboard().text()
    assert clipboard_text.startswith("# Fix login\n")
    assert "## Next actions\n\ncheck cookie after refresh" in clipboard_text


def test_work_list_uses_status_filter_instead_of_sidebar(qtbot, app_context) -> None:
    active = app_context.work_items.create(CreateWorkItem(title="Active task"))
    paused = app_context.work_items.create(
        CreateWorkItem(title="Paused task", status=WorkItemStatus.PAUSED)
    )

    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert not hasattr(window, "_status_list")
    assert window.work_list._table.rowCount() == 2

    status_filter = window.work_list._status_filter
    status_filter.setCurrentIndex(status_filter.findData(WorkItemStatus.PAUSED.value))

    assert window.work_list._table.rowCount() == 1
    assert cell_text(window.work_list, 0, 1) == paused.title
    assert cell_text(window.work_list, 0, 1) != active.title


def test_finish_work_does_not_require_progress_update(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Finish directly"))
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._open_work(str(item.id))

    window.resume._finish_button.click()

    assert app_context.work_items.get(item.id).status is WorkItemStatus.COMPLETED
    assert app_context.checkpoints.get_latest(item.id) is None
    assert window.resume._save_button.isHidden()
    assert not window.resume._resume_button.isHidden()


def test_pause_and_resume_are_separate_from_progress_updates(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Lifecycle task"))
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._open_work(str(item.id))

    window.resume._pause_button.click()
    assert app_context.work_items.get(item.id).status is WorkItemStatus.PAUSED
    assert app_context.checkpoints.get_latest(item.id) is None

    window.resume._resume_button.click()
    assert app_context.work_items.get(item.id).status is WorkItemStatus.ACTIVE
    assert app_context.checkpoints.get_latest(item.id) is None


def test_checkpoint_dialog_saves(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))

    dialog = CheckpointDialog(app_context, item)
    qtbot.addWidget(dialog)
    dialog._stopped.setPlainText("integration test failing")
    dialog._next.setPlainText("check cookie")

    assert dialog._save() is True

    checkpoint = app_context.checkpoints.get_latest(item.id)
    assert checkpoint is not None
    assert checkpoint.next_actions == "check cookie"


def test_quick_capture_selects_work_and_saves_update(qtbot, app_context) -> None:
    first = app_context.work_items.create(CreateWorkItem(title="First"))
    second = app_context.work_items.create(CreateWorkItem(title="Second"))
    dialog = QuickCaptureDialog(app_context, [first, second], second.id)
    qtbot.addWidget(dialog)

    assert dialog.selected_work_item_id() == second.id
    dialog._stopped.setPlainText("Paused at the failing test")
    dialog._next.setPlainText("Inspect the response")
    assert dialog._save()

    latest = app_context.resume.get(second.id).latest_checkpoint
    assert latest is not None
    assert latest.stopped_at == "Paused at the failing test"


def test_command_palette_filters_and_runs_command(qtbot) -> None:
    called: list[str] = []
    dialog = CommandPaletteDialog(
        [
            PaletteEntry("New work", "Action", lambda: called.append("new")),
            PaletteEntry("Quick capture", "Action", lambda: None),
            PaletteEntry("Fix login", "Work", lambda: None, detail="Active · Authentication"),
        ]
    )
    qtbot.addWidget(dialog)

    dialog._search.setText("new")
    assert dialog._list.count() == 1
    dialog._run_selected()

    assert called == ["new"]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_command_palette_searches_work_metadata_and_moves_selection(qtbot) -> None:
    dialog = CommandPaletteDialog(
        [
            PaletteEntry("Quick capture", "Action", lambda: None),
            PaletteEntry(
                "Fix login",
                "Work",
                lambda: None,
                detail="Paused · Authentication",
                keywords="cookie refresh",
            ),
        ]
    )
    qtbot.addWidget(dialog)

    dialog._search.setText("cookie")
    assert len(dialog._visible_entries) == 1
    assert dialog._visible_entries[0].label == "Fix login"
    dialog._search.clear()
    dialog._move_selection(1)
    assert dialog._list.currentRow() == 1


def test_main_command_palette_covers_current_work_and_reference_actions(
    qtbot, app_context, monkeypatch
) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login", group_name="Auth"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="Refresh still fails",
            next_actions="Inspect cookies",
        )
    )
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Login docs",
            target="https://example.com/login",
        )
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    captured: list[PaletteEntry] = []

    def capture(dialog: CommandPaletteDialog) -> int:
        captured.extend(dialog._entries)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(CommandPaletteDialog, "exec", capture)
    window._show_command_palette()

    labels = {entry.label for entry in captured}
    assert {
        "Update current work",
        "Copy handoff…",
        "Add reference…",
        "Progress history",
        "Set follow-up…",
        "Pin current work",
        "Pause current work",
        "Finish current work",
        "Archive current work",
        "Delete current work…",
        "Open reference: Login docs",
        "Edit reference: Login docs",
        "Delete reference: Login docs",
        "Edit latest progress update…",
        "Delete latest progress update…",
        "Back up data…",
        "Restore data…",
        "Export JSON…",
        "Filter: Active",
        "Group: Auth",
        "Theme: Dark",
    } <= labels


def test_follow_up_dialog_uses_readable_fields_and_presets(qtbot) -> None:
    current = QDateTime.currentDateTime().addDays(2)
    dialog = FollowUpDialog(current)
    qtbot.addWidget(dialog)

    assert dialog._date.displayFormat() == "ddd, MMM d, yyyy"
    assert dialog._time.isEditable()
    assert dialog._time.findText("09:30") >= 0
    assert dialog._date.calendarWidget().minimumWidth() >= 380
    dialog._time.setEditText("23:45")
    assert dialog.value().time().toString("HH:mm") == "23:45"
    dialog._set_offset(7)
    assert dialog.value().date() == QDateTime.currentDateTime().addDays(7).date()


def test_checkpoint_dialog_shows_inline_error(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))

    dialog = CheckpointDialog(app_context, item)
    qtbot.addWidget(dialog)
    dialog._stopped.setPlainText("   ")

    assert dialog._save() is False
    assert not dialog._errors["stopped_at"][1].isHidden()
    assert app_context.checkpoints.get_latest(item.id) is None


def test_work_editor_creates_work_item(qtbot, app_context) -> None:
    dialog = WorkEditorDialog(app_context)
    qtbot.addWidget(dialog)
    dialog._title.setText("New task")
    dialog._group.setCurrentText("Work")

    assert dialog._save() is True

    items = app_context.work_items.list_items()
    assert [item.title for item in items] == ["New task"]
    assert items[0].group_name == "Work"


def test_edit_details_does_not_offer_or_change_status(qtbot, app_context) -> None:
    item = app_context.work_items.create(
        CreateWorkItem(title="Paused task", status=WorkItemStatus.PAUSED)
    )
    dialog = WorkEditorDialog(app_context, item)
    qtbot.addWidget(dialog)

    assert dialog._status is None
    dialog._title.setText("Renamed task")
    assert dialog._save() is True

    updated = app_context.work_items.get(item.id)
    assert updated.title == "Renamed task"
    assert updated.status is WorkItemStatus.PAUSED


def test_reference_dialog_rejects_bad_url(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    dialog = ReferenceDialog(app_context, item.id)
    qtbot.addWidget(dialog)
    dialog._type.setCurrentIndex(dialog._type.findData(ReferenceType.URL))
    dialog._label.setText("Bad link")
    dialog._target.setText("ftp://example.com")

    assert dialog._save() is False
    assert not dialog._errors["target"][1].isHidden()
    assert app_context.references.list_for_work_item(item.id) == []


def test_main_window_opens_resume_view(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Fix login"))

    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert window.work_list._table.rowCount() == 1

    window._open_work(str(item.id))

    assert window._stack.currentWidget() is window.resume
    assert window.resume._title.text() == "Fix login"


def test_back_to_work_preserves_list_state(qtbot, app_context) -> None:
    item = app_context.work_items.create(
        CreateWorkItem(title="Paused login", status=WorkItemStatus.PAUSED)
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    status_filter = window.work_list._status_filter
    status_filter.setCurrentIndex(status_filter.findData(WorkItemStatus.PAUSED.value))
    window.work_list._search.setText("login")
    window.work_list.refresh()
    selected_before = window.work_list.selected_work_item_id()

    window._open_work(str(item.id))
    window.resume.back_requested.emit()

    assert window._stack.currentWidget() is window.work_list
    assert status_filter.currentData() == WorkItemStatus.PAUSED.value
    assert window.work_list._search.text() == "login"
    assert window.work_list.selected_work_item_id() == selected_before


def test_history_back_returns_to_work_detail(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._open_work(str(item.id))
    window._open_history(str(item.id))

    window.history.back_requested.emit()

    assert window._stack.currentWidget() is window.resume
    assert window.resume.current_work_item_id() == item.id


def test_settings_back_returns_to_work_list(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.work_list._search.setText("keep this search")
    window._show_settings()

    window.settings.back_requested.emit()

    assert window._stack.currentWidget() is window.work_list
    assert window.work_list._search.text() == "keep this search"
