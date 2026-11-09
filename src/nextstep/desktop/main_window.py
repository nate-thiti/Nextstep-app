"""Main window: primary navigation and the content stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nextstep.desktop.context import AppContext
from nextstep.desktop.dialogs import (
    CheckpointDialog,
    DeleteWorkItemDialog,
    FollowUpDialog,
    QuickCaptureDialog,
    WorkEditorDialog,
)
from nextstep.desktop.history_view import HistoryView
from nextstep.desktop.resume_view import ResumeView
from nextstep.desktop.settings_view import SettingsView
from nextstep.desktop.theme import apply_theme
from nextstep.desktop.widgets import make_button, show_error
from nextstep.desktop.work_list import WorkListView
from nextstep.domain.entities import WorkItem
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import NextStepError


@dataclass(frozen=True)
class PaletteEntry:
    label: str
    category: str
    callback: Callable[[], None]
    detail: str = ""
    shortcut: str = ""
    keywords: str = ""
    enabled: bool = True
    disabled_reason: str = ""


class _PaletteRow(QWidget):
    def __init__(self, entry: PaletteEntry) -> None:
        super().__init__()
        self.setEnabled(entry.enabled)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)
        category = QLabel(entry.category.upper())
        category.setProperty("role", "paletteCategory")
        category.setFixedWidth(48)
        layout.addWidget(category)
        text = QVBoxLayout()
        text.setSpacing(1)
        label = QLabel(entry.label)
        label.setProperty("role", "paletteTitle")
        text.addWidget(label)
        detail_text = entry.disabled_reason if not entry.enabled else entry.detail
        if detail_text:
            detail = QLabel(detail_text)
            detail.setProperty("role", "muted")
            text.addWidget(detail)
        layout.addLayout(text, 1)
        if entry.shortcut:
            shortcut = QLabel(entry.shortcut)
            shortcut.setProperty("role", "shortcut")
            layout.addWidget(shortcut)


class CommandPaletteDialog(QDialog):
    def __init__(self, entries: list[PaletteEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries = entries
        self._visible_entries: list[PaletteEntry] = []
        self.setWindowTitle("Command palette")
        self.resize(640, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        eyebrow = QLabel("GO TO OR DO ANYTHING")
        eyebrow.setProperty("role", "eyebrow")
        layout.addWidget(eyebrow)
        self._search = QLineEdit()
        self._search.setObjectName("CommandSearch")
        self._search.setPlaceholderText("Search commands, work, groups…")
        self._search.textChanged.connect(self._render)
        self._search.returnPressed.connect(self._run_selected)
        layout.addWidget(self._search)
        self._list = QListWidget()
        self._list.setObjectName("CommandResults")
        self._list.itemActivated.connect(lambda _item: self._run_selected())
        layout.addWidget(self._list)
        self._empty = QLabel("No matching command or work item")
        self._empty.setProperty("role", "muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        layout.addWidget(self._empty)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("↑↓  Navigate     Enter  Open"))
        footer.addStretch(1)
        escape = QLabel("Esc  Close")
        escape.setProperty("role", "muted")
        footer.addWidget(escape)
        layout.addLayout(footer)

        for key, offset in ((Qt.Key.Key_Down, 1), (Qt.Key.Key_Up, -1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda step=offset: self._move_selection(step))
        self._render()
        self._search.setFocus()

    def _render(self, query: str = "") -> None:
        self._list.clear()
        needle = query.casefold().strip()
        self._visible_entries = [
            entry
            for entry in self._entries
            if not needle
            or needle
            in " ".join((entry.label, entry.category, entry.detail, entry.keywords)).casefold()
        ]
        for entry in self._visible_entries:
            item = QListWidgetItem()
            if not entry.enabled:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setSizeHint(_PaletteRow(entry).sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, _PaletteRow(entry))
        has_results = bool(self._visible_entries)
        self._list.setVisible(has_results)
        self._empty.setVisible(not has_results)
        if has_results:
            self._select_first_enabled()

    def _run_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._visible_entries):
            return
        entry = self._visible_entries[row]
        if not entry.enabled:
            return
        callback = entry.callback
        self.accept()
        callback()

    def _move_selection(self, step: int) -> None:
        if not self._visible_entries:
            return
        row = self._list.currentRow()
        candidate = row
        while True:
            candidate += step
            if candidate < 0 or candidate >= len(self._visible_entries):
                return
            if self._visible_entries[candidate].enabled:
                self._list.setCurrentRow(candidate)
                return

    def _select_first_enabled(self) -> None:
        for row, entry in enumerate(self._visible_entries):
            if entry.enabled:
                self._list.setCurrentRow(row)
                return
        self._list.setCurrentRow(-1)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._group_filter: str | None = None
        self._syncing_filters = False
        self._current_work_id: UUID | None = None

        self.setWindowTitle("NextStep")
        self.resize(1120, 740)
        self.setMinimumSize(900, 600)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self.work_list = WorkListView(ctx)
        self.resume = ResumeView(ctx)
        self.history = HistoryView(ctx)
        self.settings = SettingsView(ctx)
        for view in (self.work_list, self.resume, self.history, self.settings):
            self._stack.addWidget(view)

        self._connect_views()
        self._install_shortcuts()

        self._refresh_groups()
        self.work_list.refresh()
        self.statusBar().showMessage(f"Data: {ctx.paths.root}")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 14, 8, 12)
        layout.setSpacing(2)

        title = QLabel("NextStep")
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)

        work_label = QLabel("WORK")
        work_label.setObjectName("SidebarSection")
        layout.addWidget(work_label)

        all_work_button = make_button("All work")
        all_work_button.clicked.connect(self._show_all_work)
        layout.addWidget(all_work_button)

        due_button = make_button("Due to resume")
        due_button.clicked.connect(self._show_due_work)
        layout.addWidget(due_button)

        quick_capture_button = make_button("Quick capture")
        quick_capture_button.clicked.connect(self._quick_capture)
        layout.addWidget(quick_capture_button)

        group_label = QLabel("GROUPS")
        group_label.setObjectName("SidebarSection")
        layout.addWidget(group_label)

        self._group_list = QListWidget()
        self._group_list.setFrameShape(QFrame.Shape.NoFrame)
        self._group_list.currentRowChanged.connect(self._group_selected)
        layout.addWidget(self._group_list, 1)

        settings_button = make_button("Settings")
        settings_button.clicked.connect(self._show_settings)
        layout.addWidget(settings_button)

        return sidebar

    def _connect_views(self) -> None:
        self.work_list.work_item_opened.connect(self._open_work)
        self.work_list.checkpoint_requested.connect(self._save_checkpoint)
        self.work_list.edit_requested.connect(self._edit_work)
        self.work_list.delete_requested.connect(self._delete_work)
        self.work_list.archive_requested.connect(self._archive_work)
        self.work_list.status_change_requested.connect(self._change_work_status)
        self.work_list.pin_requested.connect(self._set_work_pinned)
        self.work_list.follow_up_requested.connect(self._set_follow_up)
        self.work_list.new_work_requested.connect(self._new_work)

        self.resume.checkpoint_requested.connect(self._save_checkpoint)
        self.resume.back_requested.connect(self._return_to_list)
        self.resume.edit_requested.connect(self._edit_work)
        self.resume.history_requested.connect(self._open_history)
        self.resume.resume_requested.connect(self._resume_work)
        self.resume.status_change_requested.connect(self._change_work_status)

        self.history.changed.connect(self._after_checkpoint_change)
        self.history.back_requested.connect(self._return_to_detail)
        self.settings.back_requested.connect(self._return_to_list)
        self.settings.theme_changed.connect(self._apply_theme)
        self.settings.work_list_view_changed.connect(self.work_list.set_view_mode)

    def _install_shortcuts(self) -> None:
        shortcuts = (
            ("Ctrl+N", self._new_work),
            ("Ctrl+F", self.work_list.focus_search),
            ("Ctrl+Shift+U", self._checkpoint_for_current),
            ("Ctrl+Alt+U", self._quick_capture),
            ("Ctrl+K", self._show_command_palette),
            ("Esc", self._navigate_back),
        )
        for sequence, handler in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)

    # ------------------------------------------------------------------ filters

    def _group_selected(self, row: int) -> None:
        if self._syncing_filters or row < 0:
            return
        group = self._group_list.item(row).text()

        self._group_filter = group
        self._apply_filters()
        self._show_list()

    def _apply_filters(self) -> None:
        heading = f"Group — {self._group_filter}" if self._group_filter is not None else "All work"
        self.work_list.set_filter(None, self._group_filter, heading)

    def _refresh_groups(self) -> None:
        try:
            groups = self._ctx.work_items.list_groups()
        except NextStepError as error:
            show_error(self, error)
            return

        self._syncing_filters = True
        self._group_list.clear()
        for group in groups:
            self._group_list.addItem(group)
        if self._group_filter is not None:
            matches = self._group_list.findItems(self._group_filter, Qt.MatchFlag.MatchExactly)
            if matches:
                self._group_list.setCurrentRow(self._group_list.row(matches[0]))
            else:
                self._group_filter = None
                self._apply_filters()
        self._syncing_filters = False

    # --------------------------------------------------------------- navigation

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self.work_list)

    def _show_all_work(self) -> None:
        self._syncing_filters = True
        self._group_list.setCurrentRow(-1)
        self._syncing_filters = False
        self._group_filter = None
        self._apply_filters()
        self._show_list()

    def _show_due_work(self) -> None:
        due_ids = self._ctx.settings.due_work_item_ids(datetime.now(UTC))
        self.work_list.set_work_item_ids(list(due_ids), "Due to resume")
        self._show_list()

    def _show_settings(self) -> None:
        self.settings.refresh_mcp_items()
        self.settings.refresh_audit_log()
        self._stack.setCurrentWidget(self.settings)

    def _return_to_list(self) -> None:
        self._show_list()

    def _return_to_detail(self) -> None:
        if self._current_work_id is not None:
            self.resume.load(self._current_work_id)
            self._stack.setCurrentWidget(self.resume)

    def _navigate_back(self) -> None:
        current = self._stack.currentWidget()
        if current is self.history:
            self._return_to_detail()
        elif current is self.resume or current is self.settings:
            self._return_to_list()

    def _open_work(self, work_item_id: str) -> None:
        try:
            self._current_work_id = UUID(work_item_id)
            self.resume.load(self._current_work_id)
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return
        self._stack.setCurrentWidget(self.resume)

    def _open_history(self, work_item_id: str) -> None:
        try:
            self.history.load(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return
        self._stack.setCurrentWidget(self.history)

    # ------------------------------------------------------------------- actions

    def _new_work(self) -> None:
        dialog = WorkEditorDialog(self._ctx, parent=self)
        dialog.saved.connect(self._created_work)
        dialog.exec()

    def _created_work(self, work_item_id: str) -> None:
        self._refresh_groups()
        self.work_list.refresh()
        self._open_work(work_item_id)

    def _edit_work(self, work_item_id: str) -> None:
        try:
            work_item = self._ctx.work_items.get(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return

        dialog = WorkEditorDialog(self._ctx, work_item, parent=self)
        dialog.saved.connect(lambda _id: self._after_work_change(work_item_id))
        dialog.exec()

    def _after_work_change(self, work_item_id: str) -> None:
        self._refresh_groups()
        self.work_list.refresh()
        if self._stack.currentWidget() is self.resume:
            self.resume.load(UUID(work_item_id))

    def _save_checkpoint(self, work_item_id: str) -> None:
        try:
            work_item = self._ctx.work_items.get(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return

        dialog = CheckpointDialog(self._ctx, work_item, parent=self)
        dialog.saved.connect(lambda _id: self._after_checkpoint_change(work_item_id))
        dialog.exec()

    def _checkpoint_for_current(self) -> None:
        selected_id = (
            self.work_list.selected_work_item_id()
            if self._stack.currentWidget() is self.work_list
            else self._current_work_id
        )
        if selected_id is not None:
            self._save_checkpoint(str(selected_id))

    def _quick_capture(self) -> None:
        try:
            work_items = [
                item
                for item in self._ctx.work_items.list_all()
                if item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
            ]
        except NextStepError as error:
            show_error(self, error)
            return

        if not work_items:
            QMessageBox.information(
                self,
                "No open work",
                "Create or resume a Work Item before capturing progress.",
            )
            return

        selected_id = self._current_work_id or self.work_list.selected_work_item_id()
        dialog = QuickCaptureDialog(self._ctx, work_items, selected_id, self)
        dialog.saved.connect(
            lambda _checkpoint_id: self._after_checkpoint_change(
                str(dialog.selected_work_item_id())
            )
        )
        dialog.exec()

    def _show_command_palette(self) -> None:
        entries = [
            PaletteEntry("New work", "Create", self._new_work, shortcut="Ctrl+N"),
            PaletteEntry("Quick capture", "Create", self._quick_capture, shortcut="Ctrl+Alt+U"),
            PaletteEntry("Show all work", "Navigate", self._show_all_work, detail="Work list"),
            PaletteEntry(
                "Show due to resume",
                "Navigate",
                self._show_due_work,
                detail="Follow-ups that are ready now",
            ),
            PaletteEntry("Open settings", "Navigate", self._show_settings),
            PaletteEntry("Go back", "Navigate", self._navigate_back, shortcut="Esc"),
            PaletteEntry(
                "Focus work search", "Navigate", self._focus_work_search, shortcut="Ctrl+F"
            ),
            PaletteEntry("Focus view", "View", lambda: self._set_work_list_view("focus")),
            PaletteEntry("Compact view", "View", lambda: self._set_work_list_view("compact")),
            PaletteEntry(
                "Filter: Active", "Filter", lambda: self._show_status(WorkItemStatus.ACTIVE)
            ),
            PaletteEntry(
                "Filter: Paused", "Filter", lambda: self._show_status(WorkItemStatus.PAUSED)
            ),
            PaletteEntry(
                "Filter: Completed", "Filter", lambda: self._show_status(WorkItemStatus.COMPLETED)
            ),
            PaletteEntry(
                "Filter: Archived", "Filter", lambda: self._show_status(WorkItemStatus.ARCHIVED)
            ),
            PaletteEntry("Theme: System", "Appearance", lambda: self._set_theme("system")),
            PaletteEntry("Theme: Light", "Appearance", lambda: self._set_theme("light")),
            PaletteEntry("Theme: Dark", "Appearance", lambda: self._set_theme("dark")),
            PaletteEntry("Open data folder", "Data", self.settings.open_data_folder),
            PaletteEntry("Back up data…", "Data", self.settings.backup),
            PaletteEntry("Restore data…", "Data", self.settings.restore),
            PaletteEntry("Export JSON…", "Data", self.settings.export_json),
            PaletteEntry("Refresh MCP activity", "AI access", self._refresh_mcp_activity),
            PaletteEntry(
                "Load more work items",
                "Navigate",
                self.work_list.load_more,
                enabled=self.work_list.can_load_more(),
                disabled_reason="All matching work items are already loaded",
            ),
        ]
        entries.extend(
            PaletteEntry(
                f"Group: {group}",
                "Filter",
                lambda group_name=group: self._show_group(group_name),
                keywords=f"project workspace {group}",
            )
            for group in self._ctx.work_items.list_groups()
        )
        selected_id = self._current_work_id or self.work_list.selected_work_item_id()
        current = self._ctx.work_items.get(selected_id) if selected_id is not None else None
        entries[2:2] = self._current_work_palette_entries(current)
        if current is not None:
            context = self._ctx.resume.get(current.id)
            for reference in context.references:
                reference_id = reference.id
                entries.extend(
                    (
                        PaletteEntry(
                            f"Open reference: {reference.label}",
                            "Reference",
                            lambda ref_id=reference_id, work_id=str(current.id): (
                                self._reference_action(work_id, ref_id, "open")
                            ),
                            detail=reference.target,
                            keywords=reference.type.value,
                        ),
                        PaletteEntry(
                            f"Edit reference: {reference.label}",
                            "Reference",
                            lambda ref_id=reference_id, work_id=str(current.id): (
                                self._reference_action(work_id, ref_id, "edit")
                            ),
                            detail=reference.target,
                        ),
                        PaletteEntry(
                            f"Delete reference: {reference.label}",
                            "Reference",
                            lambda ref_id=reference_id, work_id=str(current.id): (
                                self._reference_action(work_id, ref_id, "delete")
                            ),
                            detail="Deletes the pointer, not the target file",
                        ),
                    )
                )
        try:
            work_items = self._ctx.work_items.list_items(limit=100)
        except NextStepError as error:
            show_error(self, error)
            return
        entries.extend(
            PaletteEntry(
                item.title,
                "Work",
                lambda work_id=str(item.id): self._open_work(work_id),
                detail=" · ".join(
                    part
                    for part in (
                        item.status.value.capitalize(),
                        item.group_name,
                        "Pinned" if self._ctx.settings.is_work_item_pinned(item.id) else None,
                    )
                    if part
                ),
                keywords=" ".join(part for part in (item.goal, item.group_name) if part),
            )
            for item in work_items
        )
        dialog = CommandPaletteDialog(entries, self)
        dialog.exec()

    def _current_work_palette_entries(self, work_item: WorkItem | None) -> list[PaletteEntry]:
        if not isinstance(work_item, WorkItem):
            unavailable = "Select a Work Item first"
            return [
                PaletteEntry(
                    label,
                    "Current work",
                    lambda: None,
                    enabled=False,
                    disabled_reason=unavailable,
                )
                for label in (
                    "Open current work",
                    "Update current work",
                    "Edit current work",
                    "Copy handoff",
                    "Set follow-up…",
                )
            ]

        work_id = str(work_item.id)
        open_for_updates = work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
        pinned = self._ctx.settings.is_work_item_pinned(work_item.id)
        follow_up = self._ctx.settings.get_follow_up_at(work_item.id)
        entries = [
            PaletteEntry("Open current work", "Current work", lambda: self._open_work(work_id)),
            PaletteEntry(
                "Update current work",
                "Current work",
                lambda: self._save_checkpoint(work_id),
                detail="Capture where you stopped",
                shortcut="Ctrl+Shift+U",
                enabled=open_for_updates,
                disabled_reason="Resume this work before adding progress",
            ),
            PaletteEntry("Edit current work", "Current work", lambda: self._edit_work(work_id)),
            PaletteEntry(
                "Copy handoff…",
                "Current work",
                lambda: self._show_handoff(work_id),
                detail="Preview Short or Full Markdown",
            ),
            PaletteEntry("Add reference…", "Current work", lambda: self._add_reference(work_id)),
            PaletteEntry(
                "Progress history",
                "Current work",
                lambda: self._open_history(work_id),
            ),
            PaletteEntry("Set follow-up…", "Current work", lambda: self._set_follow_up(work_id)),
            PaletteEntry(
                "Unpin current work" if pinned else "Pin current work",
                "Current work",
                lambda: self._set_work_pinned(work_id, not pinned),
            ),
        ]
        if follow_up is not None:
            entries.append(
                PaletteEntry(
                    "Clear follow-up",
                    "Current work",
                    lambda: self._clear_follow_up(work_id),
                )
            )
        latest = self._ctx.resume.get(work_item.id).latest_checkpoint
        if latest is not None:
            entries.extend(
                (
                    PaletteEntry(
                        "Edit latest progress update…",
                        "Progress",
                        lambda: self._edit_latest_progress(work_id),
                    ),
                    PaletteEntry(
                        "Delete latest progress update…",
                        "Progress",
                        lambda: self._delete_latest_progress(work_id),
                        detail="Permanent deletion requires confirmation",
                    ),
                )
            )
        if work_item.status is WorkItemStatus.ACTIVE:
            entries.append(
                PaletteEntry(
                    "Pause current work",
                    "Lifecycle",
                    lambda: self._change_work_status(work_id, WorkItemStatus.PAUSED.value),
                )
            )
        else:
            entries.append(
                PaletteEntry("Resume current work", "Lifecycle", lambda: self._resume_work(work_id))
            )
        if work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED):
            entries.append(
                PaletteEntry(
                    "Finish current work",
                    "Lifecycle",
                    lambda: self._change_work_status(work_id, WorkItemStatus.COMPLETED.value),
                )
            )
        if work_item.status is not WorkItemStatus.ARCHIVED:
            entries.append(
                PaletteEntry(
                    "Archive current work", "Lifecycle", lambda: self._archive_work(work_id)
                )
            )
        entries.append(
            PaletteEntry(
                "Delete current work…",
                "Lifecycle",
                lambda: self._delete_work(work_id),
                detail="Permanent deletion requires typing the work title",
                keywords="remove destroy",
            )
        )
        return entries

    def _focus_work_search(self) -> None:
        self._show_all_work()
        self.work_list.focus_search()

    def _set_work_list_view(self, mode: str) -> None:
        self.work_list.set_view_mode(mode)
        self.settings.sync_work_list_view(mode)
        self._show_list()

    def _show_status(self, status: WorkItemStatus) -> None:
        self.work_list.set_filter(status, heading=status.value.capitalize())
        self._show_list()

    def _show_group(self, group: str) -> None:
        self._group_filter = group
        self._apply_filters()
        self._show_list()

    def _set_theme(self, theme: str) -> None:
        self._ctx.settings.set_theme(theme)
        self.settings.sync_theme(theme)
        self._apply_theme(theme)

    def _refresh_mcp_activity(self) -> None:
        self.settings.refresh_audit_log()
        self._stack.setCurrentWidget(self.settings)

    def _show_handoff(self, work_item_id: str) -> None:
        self._open_work(work_item_id)
        self.resume.show_handoff()

    def _add_reference(self, work_item_id: str) -> None:
        self._open_work(work_item_id)
        self.resume.add_reference()

    def _clear_follow_up(self, work_item_id: str) -> None:
        try:
            self._ctx.settings.set_follow_up_at(UUID(work_item_id), None)
        except ValueError as error:
            show_error(self, error)
            return
        self.work_list.refresh()

    def _reference_action(self, work_item_id: str, reference_id: UUID, action: str) -> None:
        self._open_work(work_item_id)
        if action == "open":
            self.resume.open_reference(reference_id)
        elif action == "edit":
            self.resume.edit_reference(reference_id)
        elif action == "delete":
            self.resume.delete_reference(reference_id)

    def _edit_latest_progress(self, work_item_id: str) -> None:
        self._open_history(work_item_id)
        self.history.edit_latest()

    def _delete_latest_progress(self, work_item_id: str) -> None:
        self._open_history(work_item_id)
        self.history.delete_latest()

    def _after_checkpoint_change(self, work_item_id: str) -> None:
        self._refresh_groups()
        self.work_list.refresh()
        self._open_work(work_item_id)

    def _resume_work(self, work_item_id: str) -> None:
        try:
            work_item = self._ctx.work_items.get(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return

        if work_item.needs_confirmation_to_resume:
            answer = QMessageBox.question(
                self,
                "Resume work",
                f"“{work_item.title}” is {work_item.status.value}.\nResume it and mark it active?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self._ctx.work_items.resume(UUID(work_item_id), confirm=True)
        except NextStepError as error:
            show_error(self, error)
            return

        self._refresh_groups()
        self.work_list.refresh()
        self._open_work(work_item_id)

    def _archive_work(self, work_item_id: str) -> None:
        try:
            self._ctx.work_items.archive(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return
        self.work_list.refresh()

    def _change_work_status(self, work_item_id: str, status_value: str) -> None:
        try:
            status = WorkItemStatus(status_value)
            work_item_id_value = UUID(work_item_id)
            if status is WorkItemStatus.ACTIVE:
                self._ctx.work_items.resume(work_item_id_value, confirm=True)
            else:
                self._ctx.work_items.change_status(work_item_id_value, status)
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return

        self.work_list.refresh()
        if self._current_work_id == work_item_id_value:
            self.resume.load(work_item_id_value)

    def _delete_work(self, work_item_id: str) -> None:
        try:
            work_item = self._ctx.work_items.get(UUID(work_item_id))
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return

        dialog = DeleteWorkItemDialog(work_item, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._ctx.work_items.delete(UUID(work_item_id))
        except NextStepError as error:
            show_error(self, error)
            return

        if self._current_work_id is not None and str(self._current_work_id) == work_item_id:
            self._current_work_id = None
        self._refresh_groups()
        self.work_list.refresh()
        self._show_list()

    def _set_work_pinned(self, work_item_id: str, pinned: bool) -> None:
        try:
            self._ctx.settings.set_work_item_pinned(UUID(work_item_id), pinned)
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return
        self.work_list.refresh()

    def _set_follow_up(self, work_item_id: str) -> None:
        try:
            work_id = UUID(work_item_id)
            current = self._ctx.settings.get_follow_up_at(work_id)
        except (ValueError, NextStepError) as error:
            show_error(self, error)
            return
        # PySide accepts Python datetime objects at runtime; its stub omits this overload.
        current_qt = (
            QDateTime(current)  # pyright: ignore[reportArgumentType]
            if current is not None
            else None
        )
        dialog = FollowUpDialog(current_qt, self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Rejected:
            return
        value = (
            None if result == 2 else datetime.fromtimestamp(dialog.value().toSecsSinceEpoch(), UTC)
        )
        self._ctx.settings.set_follow_up_at(work_id, value)
        self.work_list.refresh()

    # -------------------------------------------------------------------- theme

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._ctx.close()
        event.accept()
