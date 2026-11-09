"""Work Detail view and the references panel (MVP_SPEC sections 6.5 and 6.7)."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from nextstep.application.handoff import format_handoff_markdown
from nextstep.application.resume import ResumeData
from nextstep.desktop.context import AppContext
from nextstep.desktop.dialogs import ReferenceDialog
from nextstep.desktop.widgets import (
    AppComboBox,
    Card,
    StatusBadge,
    format_local,
    format_relative,
    make_button,
    section_label,
    show_error,
)
from nextstep.domain.entities import WorkReference
from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.domain.errors import NextStepError
from nextstep.infrastructure.os_open import open_reference, reference_target_exists

_TYPE_LABELS: dict[ReferenceType, str] = {
    ReferenceType.FILE: "File",
    ReferenceType.FOLDER: "Folder",
    ReferenceType.URL: "URL",
    ReferenceType.GIT_REPOSITORY: "Git repository",
}


def _body_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class HandoffPreviewDialog(QDialog):
    def __init__(self, data: ResumeData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self.setWindowTitle("Copy handoff")
        self.resize(680, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        heading = QLabel("Handoff preview")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)

        self._format = AppComboBox()
        self._format.addItem("Short — current stopping point and next actions", True)
        self._format.addItem("Full — complete context and references", False)
        self._format.currentIndexChanged.connect(self._refresh)
        layout.addWidget(self._format)

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        self._copy = make_button("Copy", variant="primary")
        self._copy.clicked.connect(self._copy_text)
        buttons.addWidget(cancel)
        buttons.addWidget(self._copy)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self, _index: int = 0) -> None:
        self._preview.setPlainText(
            format_handoff_markdown(self._data, short=bool(self._format.currentData()))
        )

    def _copy_text(self) -> None:
        QApplication.clipboard().setText(self._preview.toPlainText())
        self.accept()


class ReferencesPanel(QWidget):
    changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item_id: UUID | None = None
        self._checkpoint_id: UUID | None = None
        self._references: list[WorkReference] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(section_label("References"))
        header.addStretch(1)
        add_button = make_button("+ Add reference", variant="link")
        add_button.clicked.connect(self._add)
        header.addWidget(add_button)
        layout.addLayout(header)

        self._empty = QLabel("No references yet.")
        self._empty.setProperty("role", "muted")
        layout.addWidget(self._empty)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(2)
        layout.addLayout(self._rows)

    def set_data(
        self,
        work_item_id: UUID,
        checkpoint_id: UUID | None,
        references: list[WorkReference],
    ) -> None:
        self._work_item_id = work_item_id
        self._checkpoint_id = checkpoint_id
        self._references = references
        self._render()

    def _render(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._empty.setVisible(not self._references)

        for reference in self._references:
            missing = not reference_target_exists(reference)
            marker = "⚠ " if missing else ""
            button = make_button(
                f"{marker}{reference.label}   ·   {_TYPE_LABELS[reference.type]}",
                variant="link",
            )
            tooltip = reference.target
            if missing:
                tooltip += "\nTarget not found on this computer"
            button.setToolTip(tooltip)
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda position, ref=reference, widget=button: self._context_menu(
                    widget, position, ref
                )
            )
            button.clicked.connect(lambda _checked=False, ref=reference: self._open(ref))
            self._rows.addWidget(button)

    def _context_menu(self, widget: QWidget, position: QPoint, reference: WorkReference) -> None:
        menu = QMenu(self)
        menu.addAction("Open", lambda: self._open(reference))
        menu.addAction("Edit…", lambda: self._edit(reference))
        menu.addSeparator()
        menu.addAction("Delete…", lambda: self._delete(reference))
        menu.exec(widget.mapToGlobal(position))

    def _open(self, reference: WorkReference) -> None:
        if not reference_target_exists(reference):
            QMessageBox.warning(
                self,
                "Target not found",
                f"“{reference.label}” no longer exists at:\n{reference.target}",
            )
            return

        if self._ctx.reference_requires_confirmation(reference.id):
            answer = QMessageBox.question(
                self,
                "Open restored reference?",
                "This reference came from a restored backup.\n\n"
                f"Open “{reference.label}”?\n{reference.target}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._ctx.clear_reference_confirmation(reference.id)

        if not open_reference(reference):
            QMessageBox.warning(
                self, "Could not open", f"Windows could not open:\n{reference.target}"
            )

    def _add(self) -> None:
        if self._work_item_id is None:
            return
        dialog = ReferenceDialog(
            self._ctx,
            work_item_id=self._work_item_id,
            checkpoint_id=self._checkpoint_id,
            parent=self,
        )
        dialog.saved.connect(lambda _id: self.changed.emit())
        dialog.exec()

    def add_reference(self) -> None:
        self._add()

    def open_reference(self, reference_id: UUID) -> None:
        reference = next((item for item in self._references if item.id == reference_id), None)
        if reference is not None:
            self._open(reference)

    def edit_reference(self, reference_id: UUID) -> None:
        reference = next((item for item in self._references if item.id == reference_id), None)
        if reference is not None:
            self._edit(reference)

    def delete_reference(self, reference_id: UUID) -> None:
        reference = next((item for item in self._references if item.id == reference_id), None)
        if reference is not None:
            self._delete(reference)

    def _edit(self, reference: WorkReference) -> None:
        if self._work_item_id is None:
            return
        dialog = ReferenceDialog(
            self._ctx,
            work_item_id=self._work_item_id,
            checkpoint_id=reference.checkpoint_id,
            reference=reference,
            parent=self,
        )
        dialog.saved.connect(lambda _id: self.changed.emit())
        dialog.exec()

    def _delete(self, reference: WorkReference) -> None:
        answer = QMessageBox.question(
            self,
            "Delete reference",
            f"Delete “{reference.label}”?\nThe file itself is not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ctx.references.delete(reference.id)
        except NextStepError as error:
            show_error(self, error)
            return
        self.changed.emit()


class ResumeView(QWidget):
    back_requested = Signal()
    checkpoint_requested = Signal(str)
    edit_requested = Signal(str)
    history_requested = Signal(str)
    resume_requested = Signal(str)
    status_change_requested = Signal(str, str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item_id: UUID | None = None
        self._data: ResumeData | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        content = QVBoxLayout(container)
        content.setContentsMargins(24, 20, 24, 20)
        content.setSpacing(12)

        back_button = make_button("← Back to work")
        back_button.clicked.connect(self.back_requested.emit)
        content.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)

        header = QHBoxLayout()
        header.setSpacing(10)
        self._title = QLabel("")
        self._title.setProperty("role", "h1")
        self._title.setWordWrap(True)
        header.addWidget(self._title, 1)
        self._badge = StatusBadge(WorkItemStatus.ACTIVE)
        header.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(header)

        self._meta = QLabel("")
        self._meta.setProperty("role", "muted")
        self._meta.setWordWrap(True)
        content.addWidget(self._meta)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._save_button = make_button("Update progress", variant="primary")
        self._save_button.clicked.connect(self._emit_checkpoint)
        self._resume_button = make_button("Resume work")
        self._resume_button.clicked.connect(self._emit_resume)
        self._pause_button = make_button("Pause work")
        self._pause_button.clicked.connect(lambda: self._emit_status_change(WorkItemStatus.PAUSED))
        self._finish_button = make_button("Finish work")
        self._finish_button.clicked.connect(
            lambda: self._emit_status_change(WorkItemStatus.COMPLETED)
        )
        self._archive_button = make_button("Archive work")
        self._archive_button.clicked.connect(
            lambda: self._emit_status_change(WorkItemStatus.ARCHIVED)
        )
        edit_button = make_button("Edit details")
        edit_button.clicked.connect(self._emit_edit)
        history_button = make_button("Progress history")
        history_button.clicked.connect(self._emit_history)
        self._copy_handoff_button = make_button("Copy handoff")
        self._copy_handoff_button.clicked.connect(self._copy_handoff)
        actions.addWidget(self._save_button)
        actions.addWidget(self._resume_button)
        actions.addWidget(self._pause_button)
        actions.addWidget(self._finish_button)
        actions.addWidget(self._archive_button)
        actions.addWidget(edit_button)
        actions.addWidget(history_button)
        actions.addWidget(self._copy_handoff_button)
        actions.addStretch(1)
        content.addLayout(actions)

        self._empty_card = Card("empty")
        empty_eyebrow = QLabel("READY FOR THE FIRST HANDOFF")
        empty_eyebrow.setProperty("role", "eyebrow")
        self._empty_card.body.addWidget(empty_eyebrow)
        empty_header = QHBoxLayout()
        empty_title = QLabel("No progress update yet")
        empty_title.setProperty("role", "h2")
        empty_header.addWidget(empty_title, 1)
        self._empty_update_button = make_button("Add first update", variant="primary")
        self._empty_update_button.clicked.connect(self._emit_checkpoint)
        empty_header.addWidget(self._empty_update_button)
        self._empty_card.body.addLayout(empty_header)
        empty_text = QLabel(
            "Capture where you stopped and what comes next. This becomes the point "
            "you can continue from later."
        )
        empty_text.setProperty("role", "muted")
        empty_text.setWordWrap(True)
        self._empty_card.body.addWidget(empty_text)
        content.addWidget(self._empty_card)

        self._goal_card, self._goal_text = self._make_card(content, "Goal", role="goal")
        self._goal_text.setProperty("role", "goalText")
        self._next_card, self._next_text = self._make_card(content, "Next action", role="next")
        self._next_text.setProperty("role", "h2")
        self._stopped_card, self._stopped_text = self._make_card(content, "Current stopping point")
        self._blockers_card, self._blockers_text = self._make_card(
            content, "Blockers", role="warning"
        )
        self._completed_card, self._completed_text = self._make_card(
            content, "Progress since last update"
        )

        self._timeline_card = Card("card")
        self._timeline_title = section_label("Progress timeline")
        self._timeline_card.body.addWidget(self._timeline_title)
        self._timeline = QListWidget()
        self._timeline.setAlternatingRowColors(True)
        self._timeline.setMaximumHeight(220)
        self._timeline.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._timeline_card.body.addWidget(self._timeline)
        content.addWidget(self._timeline_card)

        self._references = ReferencesPanel(ctx)
        self._references.changed.connect(self._reload)
        content.addWidget(self._references)

        content.addStretch(1)

    @staticmethod
    def _make_card(layout: QVBoxLayout, title: str, role: str = "card") -> tuple[Card, QLabel]:
        card = Card(role)
        card.body.addWidget(section_label(title))
        text = _body_label()
        card.body.addWidget(text)
        layout.addWidget(card)
        return card, text

    def load(self, work_item_id: UUID) -> None:
        self._work_item_id = work_item_id
        self._reload()

    def _reload(self) -> None:
        if self._work_item_id is None:
            return
        try:
            data = self._ctx.resume.get(self._work_item_id)
        except NextStepError as error:
            show_error(self, error)
            return
        self._render(data)

    def _render(self, data: ResumeData) -> None:
        self._data = data
        work_item = data.work_item
        checkpoint = data.latest_checkpoint

        self._title.setText(work_item.title)
        self._badge.set_status(work_item.status)

        meta_parts: list[str] = []
        if work_item.group_name:
            meta_parts.append(work_item.group_name)
        if checkpoint is not None:
            meta_parts.append(
                f"Last updated {format_local(checkpoint.created_at)} "
                f"({format_relative(checkpoint.created_at)})"
            )
        else:
            meta_parts.append("No progress update yet")
        self._meta.setText("   ·   ".join(meta_parts))

        self._empty_card.setVisible(checkpoint is None)
        self._save_button.setVisible(
            work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
        )
        self._empty_update_button.setVisible(
            work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
        )
        self._resume_button.setVisible(work_item.status is not WorkItemStatus.ACTIVE)
        self._pause_button.setVisible(work_item.status is WorkItemStatus.ACTIVE)
        self._finish_button.setVisible(
            work_item.status in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED)
        )
        self._archive_button.setVisible(work_item.status is not WorkItemStatus.ARCHIVED)

        self._goal_card.setVisible(bool(work_item.goal))
        self._goal_text.setText(work_item.goal or "")

        if checkpoint is None:
            self._next_card.hide()
            self._stopped_card.hide()
            self._blockers_card.hide()
            self._completed_card.hide()
            self._timeline_card.hide()
        else:
            self._next_card.show()
            self._next_text.setText(checkpoint.next_actions)
            self._stopped_card.show()
            self._stopped_text.setText(checkpoint.stopped_at)

            self._blockers_card.setVisible(bool(checkpoint.blockers))
            self._blockers_text.setText(checkpoint.blockers or "")

            self._completed_card.setVisible(bool(checkpoint.completed_work))
            self._completed_text.setText(checkpoint.completed_work or "")

            self._timeline.clear()
            for index, update in enumerate(data.recent_checkpoints):
                prefix = "Latest" if index == 0 else format_local(update.created_at)
                text = f"{prefix}  ·  {update.stopped_at}\nNext: {update.next_actions}"
                item = QListWidgetItem(text)
                item.setToolTip(text)
                self._timeline.addItem(item)
            self._timeline_title.setText(
                f"Progress timeline · {len(data.recent_checkpoints)} recent"
            )
            self._timeline_card.show()

        self._references.set_data(
            work_item.id,
            checkpoint.id if checkpoint is not None else None,
            data.references,
        )

    def _emit_checkpoint(self) -> None:
        if self._work_item_id is not None:
            self.checkpoint_requested.emit(str(self._work_item_id))

    def _emit_edit(self) -> None:
        if self._work_item_id is not None:
            self.edit_requested.emit(str(self._work_item_id))

    def _emit_history(self) -> None:
        if self._work_item_id is not None:
            self.history_requested.emit(str(self._work_item_id))

    def _emit_resume(self) -> None:
        if self._work_item_id is not None:
            self.resume_requested.emit(str(self._work_item_id))

    def _emit_status_change(self, status: WorkItemStatus) -> None:
        if self._work_item_id is not None:
            self.status_change_requested.emit(str(self._work_item_id), status.value)

    def _copy_handoff(self) -> None:
        if self._data is None:
            return
        dialog = HandoffPreviewDialog(self._data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._copy_handoff_button.setText("Copied")
            QTimer.singleShot(1500, lambda: self._copy_handoff_button.setText("Copy handoff"))

    def show_handoff(self) -> None:
        self._copy_handoff()

    def add_reference(self) -> None:
        self._references.add_reference()

    def open_reference(self, reference_id: UUID) -> None:
        self._references.open_reference(reference_id)

    def edit_reference(self, reference_id: UUID) -> None:
        self._references.edit_reference(reference_id)

    def delete_reference(self, reference_id: UUID) -> None:
        self._references.delete_reference(reference_id)

    def current_work_item_id(self) -> UUID | None:
        return self._work_item_id
