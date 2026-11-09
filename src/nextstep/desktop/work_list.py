"""Work List view (MVP_SPEC section 6.2)."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nextstep.application.work_items import WorkItemSummary
from nextstep.desktop.context import AppContext
from nextstep.desktop.icons import work_indicator_icon
from nextstep.desktop.widgets import (
    STATUS_LABELS,
    AppComboBox,
    StatusBadge,
    format_local,
    format_relative,
    make_button,
    section_label,
    show_error,
)
from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import NextStepError

_COLUMNS = ("", "Title", "Status", "Group", "Next action", "Updated")
_BLOCKER_MARK = "⚠"
PAGE_SIZE = 100
FOCUS_PREVIEW_MIN_WIDTH = 840


class WorkListView(QWidget):
    work_item_opened = Signal(str)
    checkpoint_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    archive_requested = Signal(str)
    status_change_requested = Signal(str, str)
    pin_requested = Signal(str, bool)
    follow_up_requested = Signal(str)
    new_work_requested = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._status: WorkItemStatus | None = None
        self._group: str | None = None
        self._work_item_ids: list[UUID] | None = None
        self._summaries: list[WorkItemSummary] = []
        self._total = 0
        self._has_more = False
        self._view_mode = ctx.settings.get_work_list_view()
        self._selected_work_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        self._heading = QLabel("All work")
        self._heading.setProperty("role", "h1")
        header.addWidget(self._heading)
        header.addStretch(1)
        self._view_buttons = QButtonGroup(self)
        self._view_buttons.setExclusive(True)
        self._focus_view_button = self._make_view_button("Focus", "focus")
        self._compact_view_button = self._make_view_button("Compact", "compact")
        self._status_filter = AppComboBox()
        self._status_filter.setAccessibleName("Filter by status")
        self._status_filter.addItem("All statuses", "")
        for status in WorkItemStatus:
            self._status_filter.addItem(STATUS_LABELS[status], status.value)
        self._status_filter.currentIndexChanged.connect(self._status_selected)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search work, progress updates, references…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(320)
        new_button = make_button("New work", variant="primary")
        new_button.clicked.connect(self.new_work_requested.emit)
        header.addWidget(new_button)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self._search)
        toolbar.addStretch(1)
        toolbar.addWidget(self._focus_view_button)
        toolbar.addWidget(self._compact_view_button)
        toolbar.addWidget(self._status_filter)
        layout.addLayout(toolbar)

        self._subheading = QLabel("")
        self._subheading.setProperty("role", "muted")
        layout.addWidget(self._subheading)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.doubleClicked.connect(self._open_current)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setWordWrap(False)
        self._table.setIconSize(QSize(34, 18))
        self._table.installEventFilter(self)

        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 32)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 118)
        for column in (3, 5):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.currentCellChanged.connect(self._selection_changed)

        self._preview = self._build_preview()
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._table)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([620, 380])
        layout.addWidget(self._splitter, 1)

        self._empty = QLabel("")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setProperty("role", "muted")
        self._empty.setWordWrap(True)
        self._empty.hide()
        layout.addWidget(self._empty, 1)

        self._load_more = make_button("Load more")
        self._load_more.clicked.connect(self._load_next_page)
        self._load_more.hide()
        load_more_row = QHBoxLayout()
        load_more_row.addStretch(1)
        load_more_row.addWidget(self._load_more)
        layout.addLayout(load_more_row)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _text: self._search_timer.start())
        self.set_view_mode(self._view_mode, persist=False)

    def _make_view_button(self, label: str, mode: str) -> QPushButton:
        button = make_button(label, variant="chip")
        button.setCheckable(True)
        button.setProperty("view_mode", mode)
        button.clicked.connect(lambda _checked: self.set_view_mode(mode))
        self._view_buttons.addButton(button)
        return button

    def _build_preview(self) -> QWidget:
        preview = QFrame()
        preview.setProperty("role", "card")
        body = QVBoxLayout(preview)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)

        title_row = QHBoxLayout()
        self._preview_title = QLabel("Select a work item")
        self._preview_title.setProperty("role", "h2")
        self._preview_title.setWordWrap(True)
        title_row.addWidget(self._preview_title, 1)
        self._preview_status = StatusBadge(WorkItemStatus.ACTIVE)
        self._preview_status.hide()
        title_row.addWidget(self._preview_status, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(title_row)

        self._preview_goal = QLabel("Choose a work item to see where to continue.")
        self._preview_goal.setProperty("role", "muted")
        self._preview_goal.setWordWrap(True)
        body.addWidget(self._preview_goal)

        self._preview_next_label = section_label("Next action")
        self._preview_next = QLabel("—")
        self._preview_next.setWordWrap(True)
        self._preview_next.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self._preview_next_label)
        body.addWidget(self._preview_next)

        self._preview_stopped_label = section_label("Current stopping point")
        self._preview_stopped = QLabel("—")
        self._preview_stopped.setWordWrap(True)
        self._preview_stopped.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self._preview_stopped_label)
        body.addWidget(self._preview_stopped)

        self._preview_blocker_label = section_label("Blocker")
        self._preview_blocker = QLabel("")
        self._preview_blocker.setWordWrap(True)
        self._preview_blocker.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self._preview_blocker_label)
        body.addWidget(self._preview_blocker)
        self._preview_blocker_label.hide()
        self._preview_blocker.hide()

        body.addStretch(1)
        buttons = QHBoxLayout()
        self._preview_open = make_button("Open work")
        self._preview_open.clicked.connect(self._open_current)
        self._preview_update = make_button("Update progress", variant="primary")
        self._preview_update.clicked.connect(self._update_current)
        buttons.addWidget(self._preview_open)
        buttons.addWidget(self._preview_update)
        body.addLayout(buttons)
        self._preview_open.setEnabled(False)
        self._preview_update.setEnabled(False)
        return preview

    def _status_cell(self, status: WorkItemStatus) -> QWidget:
        cell = QWidget()
        cell.setObjectName("StatusCell")
        cell.setStyleSheet("#StatusCell { background: transparent; }")
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 3, 4, 3)
        badge = StatusBadge(status)
        badge.setAccessibleName(f"Status: {STATUS_LABELS[status]}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(96)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignCenter)
        return cell

    def set_view_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in ("focus", "compact"):
            return
        self._view_mode = mode
        focus = mode == "focus"
        self._focus_view_button.setChecked(focus)
        self._compact_view_button.setChecked(not focus)
        self._sync_preview_visibility()
        if persist:
            self._ctx.settings.set_work_list_view(mode)
        if focus:
            self._ensure_focus_selection()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_preview_visibility()

    def _sync_preview_visibility(self) -> None:
        show_preview = self._view_mode == "focus" and self.width() >= FOCUS_PREVIEW_MIN_WIDTH
        self._preview.setVisible(show_preview)

    def view_mode(self) -> str:
        return self._view_mode

    def set_filter(
        self,
        status: WorkItemStatus | None,
        group: str | None = None,
        heading: str | None = None,
    ) -> None:
        self._status = status
        self._group = group
        self._work_item_ids = None
        index = self._status_filter.findData(status.value if status is not None else "")
        if index >= 0 and index != self._status_filter.currentIndex():
            self._status_filter.blockSignals(True)
            self._status_filter.setCurrentIndex(index)
            self._status_filter.blockSignals(False)
        if heading:
            self._heading.setText(heading)
        self.refresh()

    def set_work_item_ids(self, work_item_ids: list[UUID], heading: str) -> None:
        self._status = None
        self._group = None
        self._work_item_ids = work_item_ids
        self._heading.setText(heading)
        self.refresh()

    def _status_selected(self, _index: int) -> None:
        value = self._status_filter.currentData()
        self._status = WorkItemStatus(value) if isinstance(value, str) and value else None
        self.refresh()

    def refresh(self) -> None:
        """Reload the first page; filters and search always start over."""
        self._load_page(offset=0, replace=True)

    def _load_next_page(self) -> None:
        if not self._has_more:
            return
        self._load_page(offset=len(self._summaries))

    def _load_page(self, *, offset: int, replace: bool = False) -> None:
        previous_selection = self._selected_work_id
        try:
            page = self._ctx.work_items.page_summaries(
                status=self._status,
                group_name=self._group,
                search=self._search.text(),
                work_item_ids=self._work_item_ids,
                limit=PAGE_SIZE,
                offset=offset,
            )
        except NextStepError as error:
            show_error(self, error)
            return
        if replace:
            self._summaries = page.summaries
        else:
            self._summaries.extend(page.summaries)
        self._total = page.total
        self._has_more = page.has_more
        pinned_ids = self._ctx.settings.get_pinned_work_item_ids()
        self._summaries.sort(key=lambda item: item.work_item.id not in pinned_ids)
        self._render()
        if replace:
            self._restore_selection(previous_selection)

    def _render(self) -> None:
        self._table.setRowCount(len(self._summaries))

        for row, summary in enumerate(self._summaries):
            work_item = summary.work_item
            latest = summary.latest_checkpoint

            blocker = QTableWidgetItem(_BLOCKER_MARK if summary.has_blocker else "")
            blocker.setForeground(Qt.GlobalColor.darkYellow)
            blocker.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, blocker)

            pinned = self._ctx.settings.is_work_item_pinned(work_item.id)
            follow_up = self._ctx.settings.get_follow_up_at(work_item.id)
            title = QTableWidgetItem(work_item.title)
            title.setIcon(work_indicator_icon(pinned=pinned, reminder=follow_up is not None))
            title.setData(Qt.ItemDataRole.UserRole, str(work_item.id))
            indicators = []
            if pinned:
                indicators.append("Pinned")
            if follow_up is not None:
                indicators.append(f"Follow-up: {format_local(follow_up)}")
            tooltip_parts = [work_item.goal or work_item.title, *indicators]
            tooltip = "\n".join(tooltip_parts)
            title.setToolTip(tooltip)
            self._table.setItem(row, 1, title)

            status = QTableWidgetItem()
            status.setData(Qt.ItemDataRole.UserRole, work_item.status.value)
            status.setToolTip(STATUS_LABELS[work_item.status])
            self._table.setItem(row, 2, status)
            self._table.setCellWidget(row, 2, self._status_cell(work_item.status))

            group = QTableWidgetItem(work_item.group_name or "")
            group.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 3, group)

            next_action = "—"
            if latest is not None:
                next_action = latest.next_actions.splitlines()[0].strip()
                if len(next_action) > 90:
                    next_action = next_action[:87] + "…"
            next_item = QTableWidgetItem(next_action)
            if latest is not None:
                next_item.setToolTip(latest.next_actions)
            self._table.setItem(row, 4, next_item)

            timestamp = latest.created_at if latest is not None else work_item.updated_at
            updated = QTableWidgetItem(format_relative(timestamp))
            updated.setToolTip(str(timestamp))
            updated.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 5, updated)

        has_rows = bool(self._summaries)
        self._table.setVisible(has_rows)
        self._splitter.setVisible(has_rows)
        self._empty.setVisible(not has_rows)
        if not has_rows:
            self._empty.setText(self._empty_message())

        loaded = len(self._summaries)
        self._load_more.setVisible(self._has_more)
        if self._has_more:
            self._load_more.setText(f"Load more ({loaded} of {self._total})")
            self._subheading.setText(f"Showing {loaded} of {self._total} work items")
        else:
            self._subheading.setText(f"{self._total} work item" + ("" if self._total == 1 else "s"))

    def _restore_selection(self, work_item_id: str | None) -> None:
        selected_row = -1
        if work_item_id is not None:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 1)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == work_item_id:
                    selected_row = row
                    break
        if selected_row < 0 and self._summaries and self._view_mode == "focus":
            selected_row = 0
        if selected_row >= 0:
            self._table.selectRow(selected_row)
            self._selection_changed(selected_row, 1, -1, -1)
        else:
            self._selected_work_id = None
            self._render_preview(None)

    def _ensure_focus_selection(self) -> None:
        if self._current_id() is None and self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._selection_changed(0, 1, -1, -1)
        else:
            self._render_preview(self._current_summary())

    def _selection_changed(
        self, _row: int, _column: int, _previous_row: int, _previous_column: int
    ) -> None:
        self._selected_work_id = self._current_id()
        self._render_preview(self._current_summary())

    def _current_summary(self) -> WorkItemSummary | None:
        work_item_id = self._current_id()
        return next(
            (summary for summary in self._summaries if str(summary.work_item.id) == work_item_id),
            None,
        )

    def _render_preview(self, summary: WorkItemSummary | None) -> None:
        if summary is None:
            self._preview_title.setText("Select a work item")
            self._preview_goal.setText("Choose a work item to see where to continue.")
            self._preview_status.hide()
            self._preview_next.setText("—")
            self._preview_stopped.setText("—")
            self._preview_blocker_label.hide()
            self._preview_blocker.hide()
            self._preview_open.setEnabled(False)
            self._preview_update.setEnabled(False)
            return

        work_item = summary.work_item
        checkpoint = summary.latest_checkpoint
        self._preview_title.setText(work_item.title)
        self._preview_goal.setText(work_item.goal or "No goal added.")
        self._preview_status.set_status(work_item.status)
        self._preview_status.show()
        self._preview_next.setText(
            checkpoint.next_actions if checkpoint else "No progress update yet."
        )
        self._preview_stopped.setText(checkpoint.stopped_at if checkpoint else "—")
        has_blocker = checkpoint is not None and bool(checkpoint.blockers)
        self._preview_blocker_label.setVisible(has_blocker)
        self._preview_blocker.setVisible(has_blocker)
        self._preview_blocker.setText((checkpoint.blockers or "") if checkpoint else "")
        self._preview_open.setEnabled(True)
        self._preview_update.setEnabled(
            work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
        )

    def _update_current(self) -> None:
        work_item_id = self._current_id()
        if work_item_id:
            self.checkpoint_requested.emit(work_item_id)

    def _empty_message(self) -> str:
        if self._search.text().strip():
            return "No work items match this search."
        if self._group is not None:
            return f"No work items in “{self._group}” yet."
        if self._status is WorkItemStatus.ACTIVE:
            return "No active work.\nCreate a work item to start tracking where you left off."
        return "Nothing here yet."

    def _current_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 1)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _open_current(self, *_args: object) -> None:
        work_item_id = self._current_id()
        if work_item_id:
            self.work_item_opened.emit(work_item_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_current()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self._table
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self._open_current()
            return True
        return super().eventFilter(watched, event)

    def _show_context_menu(self, position: QPoint) -> None:
        row = self._table.rowAt(position.y())
        if row < 0:
            return
        self._table.selectRow(row)
        work_item_id = self._current_id()
        if not work_item_id:
            return

        summary = next(
            (item for item in self._summaries if str(item.work_item.id) == work_item_id),
            None,
        )
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.work_item_opened.emit(work_item_id))
        if summary is not None and summary.work_item.status in (
            WorkItemStatus.ACTIVE,
            WorkItemStatus.PAUSED,
        ):
            menu.addAction("Update progress", lambda: self.checkpoint_requested.emit(work_item_id))
        menu.addAction("Edit details", lambda: self.edit_requested.emit(work_item_id))
        if summary is not None:
            pinned = self._ctx.settings.is_work_item_pinned(summary.work_item.id)
            menu.addAction(
                "Unpin work" if pinned else "Pin work",
                lambda: self.pin_requested.emit(work_item_id, not pinned),
            )
            menu.addAction("Set follow-up…", lambda: self.follow_up_requested.emit(work_item_id))
            status = summary.work_item.status
            menu.addSeparator()
            if status is WorkItemStatus.ACTIVE:
                menu.addAction(
                    "Pause work",
                    lambda: self.status_change_requested.emit(
                        work_item_id, WorkItemStatus.PAUSED.value
                    ),
                )
            else:
                menu.addAction(
                    "Resume work",
                    lambda: self.status_change_requested.emit(
                        work_item_id, WorkItemStatus.ACTIVE.value
                    ),
                )
            if status is not WorkItemStatus.COMPLETED:
                menu.addAction(
                    "Finish work",
                    lambda: self.status_change_requested.emit(
                        work_item_id, WorkItemStatus.COMPLETED.value
                    ),
                )
            if status is not WorkItemStatus.ARCHIVED:
                menu.addAction("Archive work", lambda: self.archive_requested.emit(work_item_id))
        menu.addSeparator()
        menu.addAction("Delete…", lambda: self.delete_requested.emit(work_item_id))
        menu.exec(self._table.viewport().mapToGlobal(position))

    def selected_work_item_id(self) -> UUID | None:
        work_item_id = self._current_id()
        return UUID(work_item_id) if work_item_id else None

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def can_load_more(self) -> bool:
        return self._has_more

    def load_more(self) -> None:
        self._load_next_page()
