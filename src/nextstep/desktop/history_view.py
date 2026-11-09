"""Progress update history timeline (MVP_SPEC section 6.6)."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from nextstep.desktop.context import AppContext
from nextstep.desktop.dialogs import CheckpointDialog
from nextstep.desktop.widgets import (
    STATUS_LABELS,
    Card,
    format_local,
    make_button,
    section_label,
    show_error,
)
from nextstep.domain.entities import Checkpoint, WorkItem
from nextstep.domain.errors import NextStepError


class HistoryView(QWidget):
    changed = Signal(str)
    back_requested = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item_id: UUID | None = None
        self._work_item: WorkItem | None = None
        self._checkpoints: list[Checkpoint] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        back_button = make_button("← Back to work detail")
        back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._heading = QLabel("Progress history")
        self._heading.setProperty("role", "h1")
        layout.addWidget(self._heading)

        self._subheading = QLabel("")
        self._subheading.setProperty("role", "muted")
        layout.addWidget(self._subheading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.currentRowChanged.connect(self._render_selected)
        splitter.addWidget(self._list)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_container = QWidget()
        detail_scroll.setWidget(detail_container)
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(16, 0, 0, 0)
        detail_layout.setSpacing(10)
        splitter.addWidget(detail_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._empty = QLabel("No progress updates yet.")
        self._empty.setProperty("role", "muted")
        detail_layout.addWidget(self._empty)

        self._detail_card = Card("card")
        self._detail_body = QVBoxLayout()
        self._detail_body.setSpacing(8)
        self._detail_card.body.addLayout(self._detail_body)
        detail_layout.addWidget(self._detail_card)

        self._fields: dict[str, QLabel] = {}
        for key, title in (
            ("meta", "Saved"),
            ("next_actions", "Next action"),
            ("stopped_at", "Current stopping point"),
            ("blockers", "Blockers"),
            ("completed_work", "Progress since previous update"),
            ("context_summary", "Context summary"),
        ):
            self._detail_body.addWidget(section_label(title))
            value = QLabel("")
            value.setWordWrap(True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._detail_body.addWidget(value)
            self._fields[key] = value

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._edit_button = make_button("Edit update")
        self._edit_button.clicked.connect(self._edit_selected)
        self._delete_button = make_button("Delete", variant="danger")
        self._delete_button.clicked.connect(self._delete_selected)
        buttons.addWidget(self._edit_button)
        buttons.addWidget(self._delete_button)
        self._detail_body.addLayout(buttons)

        detail_layout.addStretch(1)

    def load(self, work_item_id: UUID) -> None:
        self._work_item_id = work_item_id
        self._reload()

    def _reload(self) -> None:
        if self._work_item_id is None:
            return
        try:
            self._work_item = self._ctx.work_items.get(self._work_item_id)
            self._checkpoints = self._ctx.checkpoints.history(self._work_item_id, limit=500)
        except NextStepError as error:
            show_error(self, error)
            return

        self._heading.setText(f"Progress history — {self._work_item.title}")
        self._subheading.setText(
            f"{len(self._checkpoints)} update" + ("" if len(self._checkpoints) == 1 else "s")
        )

        self._list.clear()
        for checkpoint in self._checkpoints:
            item = QListWidgetItem(
                f"{format_local(checkpoint.created_at)}   ·   "
                f"{STATUS_LABELS[checkpoint.status_after_save]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(checkpoint.id))
            self._list.addItem(item)

        if self._checkpoints:
            self._list.setCurrentRow(0)
        else:
            self._render_selected(-1)

    def _selected_checkpoint(self) -> Checkpoint | None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._checkpoints):
            return None
        return self._checkpoints[row]

    def _render_selected(self, _row: int) -> None:
        checkpoint = self._selected_checkpoint()
        has_selection = checkpoint is not None
        self._empty.setVisible(not has_selection)
        self._detail_card.setVisible(has_selection)
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)
        if checkpoint is None:
            return

        self._fields["meta"].setText(
            f"{format_local(checkpoint.created_at)}  ·  "
            f"work status at update: {STATUS_LABELS[checkpoint.status_after_save]}"
        )
        self._fields["next_actions"].setText(checkpoint.next_actions)
        self._fields["stopped_at"].setText(checkpoint.stopped_at)
        self._fields["blockers"].setText(checkpoint.blockers or "—")
        self._fields["completed_work"].setText(checkpoint.completed_work or "—")
        self._fields["context_summary"].setText(checkpoint.context_summary or "—")

    def _edit_selected(self) -> None:
        checkpoint = self._selected_checkpoint()
        if checkpoint is None or self._work_item is None:
            return
        dialog = CheckpointDialog(self._ctx, self._work_item, checkpoint=checkpoint, parent=self)
        dialog.saved.connect(lambda _id: self._after_change())
        dialog.exec()

    def edit_latest(self) -> None:
        if self._checkpoints:
            self._list.setCurrentRow(0)
            self._edit_selected()

    def _delete_selected(self) -> None:
        checkpoint = self._selected_checkpoint()
        if checkpoint is None or self._work_item_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete progress update",
            "Delete this progress update permanently?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ctx.checkpoints.delete(checkpoint.id)
        except NextStepError as error:
            show_error(self, error)
            return
        self._after_change()

    def delete_latest(self) -> None:
        if self._checkpoints:
            self._list.setCurrentRow(0)
            self._delete_selected()

    def _after_change(self) -> None:
        self._reload()
        if self._work_item_id is not None:
            self.changed.emit(str(self._work_item_id))
