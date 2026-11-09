"""Create, edit and checkpoint dialogs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from PySide6.QtCore import QDateTime, QLocale, QRegularExpression, Qt, QTime, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from nextstep.application.dto import (
    AddReference,
    CreateWorkItem,
    SaveCheckpoint,
    UpdateCheckpoint,
    UpdateReference,
    UpdateWorkItem,
)
from nextstep.desktop.context import AppContext
from nextstep.desktop.widgets import (
    AppComboBox,
    InlineError,
    button_row,
    make_button,
    set_invalid,
    show_error,
)
from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.domain.errors import NextStepError, ValidationError

_REFERENCE_TYPE_LABELS: dict[ReferenceType, str] = {
    ReferenceType.FILE: "File",
    ReferenceType.FOLDER: "Folder",
    ReferenceType.URL: "URL",
    ReferenceType.GIT_REPOSITORY: "Git repository",
}


class BaseDialog(QDialog):
    """Dialog that protects unsaved edits and saves with Ctrl+Enter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self._dirty = False
        self._saving = False
        self._initial: tuple[Any, ...] = ()

    def _mark_dirty(self, *_args: Any) -> None:
        if not self._saving:
            self._dirty = True

    def _snapshot(self) -> tuple[Any, ...]:
        return ()

    def is_dirty(self) -> bool:
        return self._dirty and self._snapshot() != self._initial

    def _save(self) -> bool:
        raise NotImplementedError

    def _install_save_shortcuts(self) -> None:
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._save)

    def _ask_close_action(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText("Save your changes before closing?")
        box.setIcon(QMessageBox.Icon.Question)
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()

        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        if clicked is discard:
            return "discard"
        return "cancel"

    def reject(self) -> None:
        if not self.is_dirty():
            super().reject()
            return
        action = self._ask_close_action()
        if action == "discard":
            super().reject()
        elif action == "save":
            self._save()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.is_dirty():
            event.accept()
            return

        action = self._ask_close_action()
        if action == "discard" or (action == "save" and self._save()):
            event.accept()
        else:
            event.ignore()

    def _finish(self, snapshot: tuple[Any, ...]) -> None:
        self._initial = snapshot
        self._dirty = False
        self.accept()


class CheckpointDialog(BaseDialog):
    saved = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        work_item: WorkItem,
        checkpoint: Checkpoint | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item = work_item
        self._checkpoint = checkpoint
        self._errors: dict[str, tuple[QWidget, InlineError]] = {}

        self.setWindowTitle("Edit progress update" if checkpoint else "Update progress")
        self.resize(640, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("Edit progress update" if checkpoint else "Update progress")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)

        subtitle = QLabel(work_item.title)
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._stopped = self._add_text_field(
            layout,
            "Current stopping point",
            "stopped_at",
            "e.g. Integration test for expired tokens fails",
        )
        self._next = self._add_text_field(
            layout,
            "Next action",
            "next_actions",
            "e.g. Check cookie after refresh, then rerun auth tests",
        )
        self._completed = self._add_text_field(
            layout, "Progress since last update (optional)", "completed_work", ""
        )
        self._blockers = self._add_text_field(layout, "Blockers (optional)", "blockers", "")

        advanced = QGroupBox("Advanced")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QVBoxLayout(advanced)
        self._summary = QPlainTextEdit()
        self._summary.setPlaceholderText("Longer context for your future self or an AI assistant")
        self._summary.setFixedHeight(90)
        self._summary.setTabChangesFocus(True)
        self._summary.textChanged.connect(self._mark_dirty)
        advanced_layout.addWidget(self._summary)
        layout.addWidget(advanced)

        if checkpoint is not None:
            self._fill(checkpoint)

        layout.addStretch(1)

        self._save_button = make_button("Save update", variant="primary")
        self._save_button.clicked.connect(self._save)
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addLayout(button_row(cancel, self._save_button))

        self._install_save_shortcuts()
        self._initial = self._snapshot()
        self._dirty = False
        self._stopped.setFocus()

    def _add_text_field(
        self, layout: QVBoxLayout, label: str, field: str, placeholder: str
    ) -> QPlainTextEdit:
        error = InlineError()
        editor = QPlainTextEdit()
        editor.setPlaceholderText(placeholder)
        editor.setFixedHeight(74)
        editor.setTabChangesFocus(True)
        editor.textChanged.connect(self._mark_dirty)

        caption = QLabel(label)
        caption.setProperty("role", "muted")
        layout.addWidget(caption)
        layout.addWidget(editor)
        layout.addWidget(error)

        self._errors[field] = (editor, error)
        return editor

    def _fill(self, checkpoint: Checkpoint) -> None:
        self._stopped.setPlainText(checkpoint.stopped_at)
        self._next.setPlainText(checkpoint.next_actions)
        self._completed.setPlainText(checkpoint.completed_work or "")
        self._blockers.setPlainText(checkpoint.blockers or "")
        self._summary.setPlainText(checkpoint.context_summary or "")

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            self._stopped.toPlainText(),
            self._next.toPlainText(),
            self._completed.toPlainText(),
            self._blockers.toPlainText(),
            self._summary.toPlainText(),
        )

    def _clear_errors(self) -> None:
        for widget, error in self._errors.values():
            error.clear_message()
            set_invalid(widget, False)

    def _show_field_error(self, field: str, message: str) -> None:
        entry = self._errors.get(field)
        if entry is None:
            QMessageBox.warning(self, "Invalid value", message)
            return
        widget, error = entry
        error.show_message(message)
        set_invalid(widget, True)

    def _save(self) -> bool:
        if self._saving:
            return False
        self._saving = True
        self._save_button.setEnabled(False)
        self._clear_errors()
        try:
            if self._checkpoint is None:
                result = self._ctx.checkpoints.save(
                    SaveCheckpoint(
                        work_item_id=self._work_item.id,
                        stopped_at=self._stopped.toPlainText(),
                        next_actions=self._next.toPlainText(),
                        completed_work=self._completed.toPlainText(),
                        blockers=self._blockers.toPlainText(),
                        context_summary=self._summary.toPlainText(),
                    )
                )
            else:
                result = self._ctx.checkpoints.update(
                    self._checkpoint.id,
                    UpdateCheckpoint(
                        stopped_at=self._stopped.toPlainText(),
                        next_actions=self._next.toPlainText(),
                        completed_work=self._completed.toPlainText(),
                        blockers=self._blockers.toPlainText(),
                        context_summary=self._summary.toPlainText(),
                    ),
                )
        except ValidationError as error:
            self._show_field_error(error.field, error.message)
            return False
        except NextStepError as error:
            show_error(self, error)
            return False
        finally:
            self._saving = False
            self._save_button.setEnabled(True)

        self.saved.emit(str(result.id))
        self._finish(self._snapshot())
        return True


class QuickCaptureDialog(CheckpointDialog):
    """Choose an open Work Item, then capture a progress update."""

    def __init__(
        self,
        ctx: AppContext,
        work_items: list[WorkItem],
        selected_work_item_id: UUID | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if not work_items:
            raise ValueError("Quick capture requires at least one open work item")

        selected = next(
            (item for item in work_items if item.id == selected_work_item_id), work_items[0]
        )
        super().__init__(ctx, selected, parent=parent)
        self.setWindowTitle("Quick capture")

        layout = self.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        heading_item = layout.itemAt(0)
        heading = heading_item.widget() if heading_item is not None else None
        if isinstance(heading, QLabel):
            heading.setText("Quick capture")

        subtitle_item = layout.itemAt(1)
        subtitle = subtitle_item.widget() if subtitle_item is not None else None
        if isinstance(subtitle, QLabel):
            layout.removeWidget(subtitle)
            subtitle.hide()
            subtitle.setParent(None)

        self._work_picker = AppComboBox()
        for item in work_items:
            self._work_picker.addItem(item.title, item.id)
        self._work_picker.setCurrentIndex(self._work_picker.findData(selected.id))
        self._work_picker.currentIndexChanged.connect(self._select_work_item)
        layout.insertWidget(1, self._work_picker)

        self._work_items = {item.id: item for item in work_items}
        self._initial = self._snapshot()
        self._dirty = False

    def _select_work_item(self, _index: int) -> None:
        work_item_id = self._work_picker.currentData()
        if isinstance(work_item_id, UUID):
            self._work_item = self._work_items[work_item_id]
            self._mark_dirty()

    def selected_work_item_id(self) -> UUID:
        return self._work_item.id


class FollowUpDialog(QDialog):
    def __init__(self, current: QDateTime | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Follow-up reminder")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        eyebrow = QLabel("RETURN TO WORK")
        eyebrow.setProperty("role", "eyebrow")
        layout.addWidget(eyebrow)
        heading = QLabel("When should this work resurface?")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)
        description = QLabel(
            "It will appear in Due to resume once this time is reached. "
            "NextStep will not change the work status."
        )
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        selected = (current or QDateTime.currentDateTime().addDays(1)).toLocalTime()
        english = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        fields = QHBoxLayout()
        fields.setSpacing(10)
        date_column = QVBoxLayout()
        date_label = QLabel("DATE")
        date_label.setProperty("role", "section")
        date_column.addWidget(date_label)
        self._date = QDateEdit(selected.date())
        self._date.setLocale(english)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("ddd, MMM d, yyyy")
        self._date.setMinimumDate(QDateTime.currentDateTime().date())
        calendar = self._date.calendarWidget()
        calendar.setLocale(english)
        calendar.setGridVisible(False)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setMinimumSize(420, 300)
        date_column.addWidget(self._date)
        fields.addLayout(date_column, 2)

        time_column = QVBoxLayout()
        time_label = QLabel("TIME")
        time_label.setProperty("role", "section")
        time_column.addWidget(time_label)
        self._time = AppComboBox()
        self._time.setLocale(english)
        self._time.setEditable(True)
        self._time.setInsertPolicy(AppComboBox.InsertPolicy.NoInsert)
        for hour in range(24):
            for minute in (0, 30):
                self._time.addItem(f"{hour:02d}:{minute:02d}")
        self._time.setEditText(selected.time().toString("HH:mm"))
        time_editor = self._time.lineEdit()
        if time_editor is not None:
            pattern = QRegularExpression(r"(?:[01]\d|2[0-3]):[0-5]\d")
            time_editor.setValidator(QRegularExpressionValidator(pattern, self._time))
            time_editor.textChanged.connect(self._validate_time)
        time_column.addWidget(self._time)
        fields.addLayout(time_column, 1)
        layout.addLayout(fields)

        presets = QHBoxLayout()
        presets.setSpacing(6)
        for label, days in (("Tomorrow", 1), ("In 3 days", 3), ("Next week", 7)):
            button = make_button(label, variant="chip")
            button.clicked.connect(lambda _checked=False, offset=days: self._set_offset(offset))
            presets.addWidget(button)
        presets.addStretch(1)
        layout.addLayout(presets)

        layout.addSpacing(4)
        clear = make_button("Clear reminder", variant="link")
        clear.setVisible(current is not None)
        clear.clicked.connect(lambda: self.done(2))
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        self._save_button = make_button("Save reminder", variant="primary")
        self._save_button.clicked.connect(self.accept)
        layout.addLayout(button_row(clear, cancel, self._save_button))
        self._validate_time()

    def value(self) -> QDateTime:
        return QDateTime(self._date.date(), QTime.fromString(self._time.currentText(), "HH:mm"))

    def _set_offset(self, days: int) -> None:
        target = QDateTime.currentDateTime().addDays(days)
        self._date.setDate(target.date())
        self._time.setEditText(target.time().toString("HH:mm"))

    def _validate_time(self, _text: str = "") -> None:
        valid = QTime.fromString(self._time.currentText(), "HH:mm").isValid()
        set_invalid(self._time, not valid)
        if hasattr(self, "_save_button"):
            self._save_button.setEnabled(valid)


class WorkEditorDialog(BaseDialog):
    saved = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        work_item: WorkItem | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item = work_item

        self.setWindowTitle("Edit work details" if work_item else "New work item")
        self.resize(560, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("Edit work details" if work_item else "New work item")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)

        title_error = InlineError()
        self._title = QLineEdit()
        self._title.setPlaceholderText("What are you working on?")
        self._title.textChanged.connect(self._mark_dirty)
        layout.addWidget(self._caption("Title"))
        layout.addWidget(self._title)
        layout.addWidget(title_error)
        self._errors: dict[str, tuple[QWidget, InlineError]] = {"title": (self._title, title_error)}

        self._goal = QPlainTextEdit()
        self._goal.setPlaceholderText("Goal or definition of done (optional)")
        self._goal.setFixedHeight(110)
        self._goal.setTabChangesFocus(True)
        self._goal.textChanged.connect(self._mark_dirty)
        layout.addWidget(self._caption("Goal"))
        layout.addWidget(self._goal)

        self._group = AppComboBox()
        self._group.setEditable(True)
        self._group.setInsertPolicy(AppComboBox.InsertPolicy.NoInsert)
        self._group.addItem("", None)
        for group in ctx.work_items.list_groups():
            self._group.addItem(group, group)
        self._group.currentTextChanged.connect(self._mark_dirty)
        layout.addWidget(self._caption("Group (optional)"))
        layout.addWidget(self._group)

        self._status: AppComboBox | None = None
        if work_item is None:
            self._status = AppComboBox()
            self._status.addItem("Active", WorkItemStatus.ACTIVE)
            self._status.currentIndexChanged.connect(self._mark_dirty)
            layout.addWidget(self._caption("Initial status"))
            layout.addWidget(self._status)

        if work_item is not None:
            self._title.setText(work_item.title)
            self._goal.setPlainText(work_item.goal or "")
            self._group.setCurrentText(work_item.group_name or "")

        layout.addStretch(1)

        save = make_button("Save", variant="primary")
        save.clicked.connect(self._save)
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addLayout(button_row(cancel, save))

        self._install_save_shortcuts()
        self._initial = self._snapshot()
        self._dirty = False
        self._title.setFocus()

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            self._title.text(),
            self._goal.toPlainText(),
            self._group.currentText(),
            self._status.currentData() if self._status is not None else None,
        )

    def _save(self) -> bool:
        if self._saving:
            return False
        self._saving = True
        try:
            for widget, error in self._errors.values():
                error.clear_message()
                set_invalid(widget, False)

            group_text = self._group.currentText().strip()
            try:
                if self._work_item is None:
                    work_item = self._ctx.work_items.create(
                        CreateWorkItem(
                            title=self._title.text(),
                            goal=self._goal.toPlainText(),
                            group_name=group_text or None,
                            status=(
                                self._status.currentData()
                                if self._status is not None
                                else WorkItemStatus.ACTIVE
                            ),
                        )
                    )
                else:
                    work_item = self._ctx.work_items.update(
                        self._work_item.id,
                        UpdateWorkItem(
                            title=self._title.text(),
                            goal=self._goal.toPlainText(),
                            group_name=group_text or None,
                        ),
                    )
            except ValidationError as error:
                entry = self._errors.get(error.field)
                if entry is None:
                    show_error(self, error)
                else:
                    widget, label = entry
                    label.show_message(error.message)
                    set_invalid(widget, True)
                return False
            except NextStepError as error:
                show_error(self, error)
                return False
        finally:
            self._saving = False

        self.saved.emit(str(work_item.id))
        self._finish(self._snapshot())
        return True


class DeleteWorkItemDialog(QDialog):
    """Typed confirmation for permanent deletion (MVP_SPEC section 7.1)."""

    def __init__(self, work_item: WorkItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._work_item = work_item
        self.setWindowTitle("Delete work item")
        self.setModal(True)
        self.resize(540, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel(f"Delete “{work_item.title}”?")
        heading.setProperty("role", "h1")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        warning = QLabel(
            "This permanently deletes the work item, all of its checkpoints and "
            "all of its references. This cannot be undone."
        )
        warning.setWordWrap(True)
        warning.setProperty("role", "muted")
        layout.addWidget(warning)

        prompt = QLabel("Type the work item title to confirm:")
        prompt.setProperty("role", "muted")
        layout.addWidget(prompt)

        self._input = QLineEdit()
        self._input.setPlaceholderText(work_item.title)
        self._input.textChanged.connect(self._update_delete_button)
        layout.addWidget(self._input)

        self._hint = InlineError()
        layout.addWidget(self._hint)

        layout.addStretch(1)

        cancel = make_button("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        cancel.setDefault(True)
        self._delete_button = make_button("Delete permanently", variant="danger")
        self._delete_button.setAutoDefault(False)
        self._delete_button.setDefault(False)
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self.accept)
        layout.addLayout(button_row(cancel, self._delete_button))

        self._input.setFocus()

    def _update_delete_button(self, text: str) -> None:
        matches = text.strip() == self._work_item.title.strip()
        self._delete_button.setEnabled(matches)
        if text and not matches:
            self._hint.show_message("The title does not match.")
        else:
            self._hint.clear_message()

    def accept(self) -> None:
        if self._delete_button.isEnabled():
            super().accept()


class ReferenceDialog(BaseDialog):
    saved = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        work_item_id: UUID,
        checkpoint_id: UUID | None = None,
        reference: WorkReference | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._work_item_id = work_item_id
        self._checkpoint_id = checkpoint_id
        self._reference = reference
        self._metadata: dict[str, Any] = dict(reference.metadata) if reference else {}

        self.setWindowTitle("Edit reference" if reference else "Add reference")
        self.resize(560, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("Edit reference" if reference else "Add reference")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)

        self._type = AppComboBox()
        for reference_type, label in _REFERENCE_TYPE_LABELS.items():
            self._type.addItem(label, reference_type)
        self._type.currentIndexChanged.connect(self._type_changed)
        layout.addWidget(self._caption("Type"))
        layout.addWidget(self._type)

        label_error = InlineError()
        self._label = QLineEdit()
        self._label.setPlaceholderText("Short name shown in Work Detail")
        self._label.textChanged.connect(self._mark_dirty)
        layout.addWidget(self._caption("Label"))
        layout.addWidget(self._label)
        layout.addWidget(label_error)

        target_error = InlineError()
        self._target = QLineEdit()
        self._target.setPlaceholderText("Absolute path or https:// URL")
        self._target.textChanged.connect(self._mark_dirty)
        self._browse = make_button("Browse…")
        self._browse.clicked.connect(self._browse_target)
        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        target_row.addWidget(self._target, 1)
        target_row.addWidget(self._browse)
        layout.addWidget(self._caption("Target"))
        layout.addLayout(target_row)
        layout.addWidget(target_error)

        self._git_box = QWidget()
        git_layout = QVBoxLayout(self._git_box)
        git_layout.setContentsMargins(0, 0, 0, 0)
        git_layout.setSpacing(6)
        self._branch = QLineEdit(str(self._metadata.get("branch", "")))
        self._commit = QLineEdit(str(self._metadata.get("commit", "")))
        self._branch.textChanged.connect(self._mark_dirty)
        self._commit.textChanged.connect(self._mark_dirty)
        git_layout.addWidget(self._caption("Branch (optional)"))
        git_layout.addWidget(self._branch)
        git_layout.addWidget(self._caption("Commit (optional)"))
        git_layout.addWidget(self._commit)
        layout.addWidget(self._git_box)

        self._errors: dict[str, tuple[QWidget, InlineError]] = {
            "label": (self._label, label_error),
            "target": (self._target, target_error),
        }

        if reference is not None:
            index = self._type.findData(reference.type)
            if index >= 0:
                self._type.setCurrentIndex(index)
            self._type.setEnabled(False)
            self._label.setText(reference.label)
            self._target.setText(reference.target)

        self._type_changed()

        layout.addStretch(1)
        save = make_button("Save", variant="primary")
        save.clicked.connect(self._save)
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addLayout(button_row(cancel, save))

        self._install_save_shortcuts()
        self._initial = self._snapshot()
        self._dirty = False
        self._label.setFocus()

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    def _current_type(self) -> ReferenceType:
        value = self._type.currentData()
        if isinstance(value, ReferenceType):
            return value
        try:
            return ReferenceType(value)
        except (TypeError, ValueError):
            return ReferenceType.FILE

    def _type_changed(self, *_args: Any) -> None:
        is_url = self._current_type() is ReferenceType.URL
        is_git = self._current_type() is ReferenceType.GIT_REPOSITORY
        self._browse.setVisible(not is_url)
        self._git_box.setVisible(is_git)
        self._mark_dirty()

    def _browse_target(self) -> None:
        if self._current_type() in (ReferenceType.FOLDER, ReferenceType.GIT_REPOSITORY):
            selected = QFileDialog.getExistingDirectory(self, "Choose folder")
        else:
            selected, _ = QFileDialog.getOpenFileName(self, "Choose file")
        if selected:
            self._target.setText(selected)

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            self._type.currentData(),
            self._label.text(),
            self._target.text(),
            self._branch.text(),
            self._commit.text(),
        )

    def _metadata_for_save(self) -> dict[str, Any]:
        metadata = dict(self._metadata)
        if self._current_type() is ReferenceType.GIT_REPOSITORY:
            for key, value in (
                ("branch", self._branch.text().strip()),
                ("commit", self._commit.text().strip()),
            ):
                if value:
                    metadata[key] = value
                else:
                    metadata.pop(key, None)
        return metadata

    def _save(self) -> bool:
        if self._saving:
            return False
        self._saving = True
        for widget, error in self._errors.values():
            error.clear_message()
            set_invalid(widget, False)
        try:
            try:
                if self._reference is None:
                    reference = self._ctx.references.add(
                        AddReference(
                            work_item_id=self._work_item_id,
                            checkpoint_id=self._checkpoint_id,
                            type=self._current_type(),
                            label=self._label.text(),
                            target=self._target.text(),
                            metadata=self._metadata_for_save(),
                        )
                    )
                else:
                    reference = self._ctx.references.update(
                        self._reference.id,
                        UpdateReference(
                            label=self._label.text(),
                            target=self._target.text(),
                            metadata=self._metadata_for_save(),
                        ),
                    )
            except ValidationError as error:
                entry = self._errors.get(error.field)
                if entry is None:
                    show_error(self, error)
                else:
                    widget, label = entry
                    label.show_message(error.message)
                    set_invalid(widget, True)
                return False
            except NextStepError as error:
                show_error(self, error)
                return False
        finally:
            self._saving = False

        self.saved.emit(str(reference.id))
        self._finish(self._snapshot())
        return True
