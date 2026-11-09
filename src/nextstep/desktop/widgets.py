"""Small shared widgets and formatting helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nextstep.domain.enums import WorkItemStatus
from nextstep.domain.errors import NextStepError, ValidationError

logger = logging.getLogger(__name__)

STATUS_LABELS: dict[WorkItemStatus, str] = {
    WorkItemStatus.ACTIVE: "Active",
    WorkItemStatus.PAUSED: "Paused",
    WorkItemStatus.COMPLETED: "Completed",
    WorkItemStatus.ARCHIVED: "Archived",
}


def format_local(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%d %b %Y, %H:%M")


def format_relative(value: datetime | None) -> str:
    if value is None:
        return "—"
    now = datetime.now(UTC)
    delta = now - value.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    return format_local(value)


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_invalid(widget: QWidget, invalid: bool) -> None:
    widget.setProperty("invalid", "true" if invalid else "false")
    repolish(widget)


def set_button_class(button: QPushButton, name: str) -> None:
    button.setProperty("class", name)
    repolish(button)


def make_button(text: str, *, variant: str | None = None) -> QPushButton:
    button = QPushButton(text)
    if variant:
        set_button_class(button, variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class AppComboBox(QComboBox):
    """Project combo box with consistent pointer cursors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view().setCursor(Qt.CursorShape.PointingHandCursor)


class StatusBadge(QLabel):
    def __init__(self, status: WorkItemStatus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.set_status(status)

    def set_status(self, status: WorkItemStatus) -> None:
        self.setProperty("status", status.value)
        self.setText(STATUS_LABELS[status])
        repolish(self)


class InlineError(QLabel):
    """Validation message shown directly under a field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "error")
        self.setWordWrap(True)
        self.hide()

    def show_message(self, message: str) -> None:
        self.setText(message)
        self.show()

    def clear_message(self) -> None:
        self.setText("")
        self.hide()


class Card(QFrame):
    def __init__(self, role: str = "card", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", role)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("role", "section")
    return label


def separator() -> QFrame:
    line = QFrame()
    line.setProperty("role", "separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def form_row(label_text: str, field: QWidget, error: QLabel | None = None) -> QVBoxLayout:
    row = QVBoxLayout()
    row.setSpacing(4)
    label = QLabel(label_text)
    label.setProperty("role", "muted")
    row.addWidget(label)
    row.addWidget(field)
    if error is not None:
        row.addWidget(error)
    return row


def button_row(*buttons: QWidget, align_end: bool = True) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addStretch(1)
    for button in buttons:
        row.addWidget(button)
    if not align_end:
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)
    return row


def show_error(parent: QWidget, error: BaseException) -> None:
    """Present an expected error without leaking internals."""
    if isinstance(error, ValidationError):
        QMessageBox.warning(parent, "Invalid value", f"{error.field}: {error.message}")
        return
    if isinstance(error, NextStepError):
        QMessageBox.warning(parent, "Action failed", str(error))
        return
    logger.exception("unexpected error", exc_info=error)
    QMessageBox.critical(
        parent,
        "Unexpected error",
        "Something went wrong. Details were written to the local log file.",
    )
