"""Settings view (MVP_SPEC section 6.8)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from nextstep import __version__
from nextstep.application.mcp_policy import McpScope
from nextstep.application.mcp_setup import build_mcp_client_guides, resolve_mcp_command
from nextstep.desktop.context import AppContext
from nextstep.desktop.widgets import (
    STATUS_LABELS,
    AppComboBox,
    Card,
    format_local,
    make_button,
    section_label,
    show_error,
)
from nextstep.domain.entities import AuditLogEntry
from nextstep.domain.enums import McpOperation
from nextstep.domain.errors import NextStepError, RestoreRequiresRestartError
from nextstep.infrastructure.os_open import open_path

_THEME_LABELS = (("System", "system"), ("Light", "light"), ("Dark", "dark"))
_MCP_SCOPE_LABELS = (
    ("Off", McpScope.DISABLED.value),
    ("All work items", McpScope.ALL.value),
    ("Selected work items", McpScope.SELECTED.value),
)
_MCP_WRITE_LABELS = (
    (McpOperation.CREATE_WORK_ITEM, "Create work items"),
    (McpOperation.UPDATE_WORK_ITEM, "Edit work items"),
    (McpOperation.SAVE_PROGRESS_UPDATE, "Save progress updates"),
    (McpOperation.CHANGE_WORK_ITEM_STATUS, "Change work status"),
    (McpOperation.ADD_REFERENCE, "Add references"),
    (McpOperation.UPDATE_REFERENCE, "Edit references"),
    (McpOperation.DELETE_REFERENCE, "Delete references"),
)
_BACKUP_FILTER = "NextStep backup (*.zip)"
_EXPORT_FILTER = "JSON export (*.json)"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


class SettingsView(QWidget):
    back_requested = Signal()
    theme_changed = Signal(str)
    work_list_view_changed = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._loading = True
        self._loading_mcp = True
        self._loading_write = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        back_button = make_button("← Back to work")
        back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)

        heading = QLabel("Settings")
        heading.setProperty("role", "h1")
        layout.addWidget(heading)

        data_card = Card()
        data_card.body.addWidget(section_label("Data location"))
        path_label = QLabel(str(ctx.paths.root))
        path_label.setWordWrap(True)
        path_label.setTextFormat(Qt.TextFormat.PlainText)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_card.body.addWidget(path_label)
        open_button = make_button("Open data folder")
        open_button.clicked.connect(self.open_data_folder)
        data_row = QHBoxLayout()
        data_row.addWidget(open_button)
        data_row.addStretch(1)
        data_card.body.addLayout(data_row)
        layout.addWidget(data_card)

        portability = Card()
        portability.body.addWidget(section_label("Backup and export"))
        description = QLabel(
            "Backups contain only the NextStep database. Files and folders that "
            "references point to are never copied."
        )
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        portability.body.addWidget(description)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.backup_button = make_button("Back up…", variant="primary")
        self.backup_button.clicked.connect(self._backup)
        self.restore_button = make_button("Restore…")
        self.restore_button.clicked.connect(self._restore)
        self.export_button = make_button("Export JSON…")
        self.export_button.clicked.connect(self._export_json)
        buttons.addWidget(self.backup_button)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        portability.body.addLayout(buttons)
        layout.addWidget(portability)

        appearance = Card()
        appearance.body.addWidget(section_label("Appearance"))
        self._theme = AppComboBox()
        for label, value in _THEME_LABELS:
            self._theme.addItem(label, value)
        current = ctx.settings.get_theme()
        index = self._theme.findData(current)
        if index >= 0:
            self._theme.setCurrentIndex(index)
        self._theme.currentIndexChanged.connect(self._theme_selected)
        appearance.body.addWidget(self._theme)
        appearance.body.addWidget(section_label("Default work list view"))
        self.work_list_view = AppComboBox()
        self.work_list_view.addItem("Focus — list with work preview", "focus")
        self.work_list_view.addItem("Compact — full-width table", "compact")
        view_index = self.work_list_view.findData(ctx.settings.get_work_list_view())
        if view_index >= 0:
            self.work_list_view.setCurrentIndex(view_index)
        self.work_list_view.currentIndexChanged.connect(self._work_list_view_selected)
        appearance.body.addWidget(self.work_list_view)
        layout.addWidget(appearance)

        mcp_card = Card()
        mcp_card.body.addWidget(section_label("AI access (MCP)"))
        mcp_description = QLabel(
            "Allow a local MCP client to read work context. Changes stay off until "
            "you grant them below, and progress update text is never written to the log."
        )
        mcp_description.setProperty("role", "muted")
        mcp_description.setWordWrap(True)
        mcp_card.body.addWidget(mcp_description)

        self.mcp_scope = AppComboBox()
        for label, value in _MCP_SCOPE_LABELS:
            self.mcp_scope.addItem(label, value)
        policy = ctx.mcp_policy.get_policy()
        scope_index = self.mcp_scope.findData(policy.scope.value)
        if scope_index >= 0:
            self.mcp_scope.setCurrentIndex(scope_index)
        self.mcp_scope.currentIndexChanged.connect(self._mcp_scope_selected)
        mcp_card.body.addWidget(self.mcp_scope)

        self.mcp_items = QListWidget()
        self.mcp_items.setMaximumHeight(180)
        self.mcp_items.itemChanged.connect(self._mcp_selection_changed)
        mcp_card.body.addWidget(self.mcp_items)

        self.mcp_empty = QLabel("No work items yet.")
        self.mcp_empty.setProperty("role", "muted")
        mcp_card.body.addWidget(self.mcp_empty)

        self.mcp_permissions = QFrame()
        self.mcp_permissions.setProperty("role", "permissions")
        permissions_layout = QVBoxLayout(self.mcp_permissions)
        permissions_layout.setContentsMargins(14, 12, 14, 12)
        permissions_layout.setSpacing(8)

        self.mcp_write_enabled = QCheckBox("Allow MCP to change data")
        self.mcp_write_enabled.setProperty("role", "toggleTitle")
        self.mcp_write_enabled.toggled.connect(self._mcp_write_enabled_toggled)
        permissions_layout.addWidget(self.mcp_write_enabled)

        write_hint = QLabel(
            "Choose what a connected AI client may change. Work Items cannot be "
            "deleted permanently through MCP; that stays in NextStep."
        )
        write_hint.setProperty("role", "muted")
        write_hint.setWordWrap(True)
        permissions_layout.addWidget(write_hint)

        permissions_layout.addWidget(section_label("Allowed changes"))

        self.mcp_write_checks: dict[McpOperation, QCheckBox] = {}
        capability_grid = QGridLayout()
        capability_grid.setContentsMargins(0, 0, 0, 0)
        capability_grid.setHorizontalSpacing(24)
        capability_grid.setVerticalSpacing(2)
        for index, (operation, label) in enumerate(_MCP_WRITE_LABELS):
            check = QCheckBox(label)
            check.setProperty("class", "permissionOption")
            check.toggled.connect(self._mcp_write_operation_toggled)
            capability_grid.addWidget(check, index // 2, index % 2)
            self.mcp_write_checks[operation] = check
        for column in range(2):
            capability_grid.setColumnStretch(column, 1)
        permissions_layout.addLayout(capability_grid)
        mcp_card.body.addWidget(self.mcp_permissions)

        write_policy = ctx.mcp_policy.get_write_policy()
        self.mcp_write_enabled.setChecked(write_policy.enabled)
        for operation, check in self.mcp_write_checks.items():
            check.setChecked(operation in write_policy.operations)
        self._update_write_controls()

        mcp_hint = QLabel('Connect a client by running "nextstep-mcp" as a local stdio MCP server.')
        mcp_hint.setProperty("role", "muted")
        mcp_hint.setWordWrap(True)
        mcp_card.body.addWidget(mcp_hint)

        mcp_card.body.addWidget(section_label("Connect an AI client"))
        self.mcp_guides = build_mcp_client_guides(resolve_mcp_command())
        self.mcp_client = AppComboBox()
        for guide in self.mcp_guides:
            self.mcp_client.addItem(guide.label, guide.key)
        self.mcp_client.currentIndexChanged.connect(self._mcp_client_selected)
        mcp_card.body.addWidget(self.mcp_client)

        self.mcp_setup_location = QLabel("")
        self.mcp_setup_location.setProperty("role", "muted")
        self.mcp_setup_location.setWordWrap(True)
        self.mcp_setup_location.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mcp_card.body.addWidget(self.mcp_setup_location)

        self.mcp_setup_steps = QLabel("")
        self.mcp_setup_steps.setWordWrap(True)
        mcp_card.body.addWidget(self.mcp_setup_steps)

        self.mcp_setup_text = QPlainTextEdit()
        self.mcp_setup_text.setReadOnly(True)
        self.mcp_setup_text.setMaximumHeight(190)
        self.mcp_setup_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mcp_card.body.addWidget(self.mcp_setup_text)

        setup_actions = QHBoxLayout()
        self.copy_mcp_setup_button = make_button("Copy configuration", variant="primary")
        self.copy_mcp_setup_button.clicked.connect(self._copy_mcp_setup)
        setup_actions.addWidget(self.copy_mcp_setup_button)
        setup_actions.addStretch(1)
        mcp_card.body.addLayout(setup_actions)
        self._mcp_client_selected(0)
        layout.addWidget(mcp_card)

        activity = Card()
        activity.body.addWidget(section_label("MCP activity"))
        activity_description = QLabel(
            "Recent MCP changes. Only the tool, result, identifiers and changed "
            "field names are recorded — never titles, goals, progress text or URLs."
        )
        activity_description.setProperty("role", "muted")
        activity_description.setWordWrap(True)
        activity.body.addWidget(activity_description)

        self.mcp_activity = QListWidget()
        self.mcp_activity.setMaximumHeight(220)
        activity.body.addWidget(self.mcp_activity)

        self.mcp_activity_empty = QLabel("No MCP activity yet.")
        self.mcp_activity_empty.setProperty("role", "muted")
        activity.body.addWidget(self.mcp_activity_empty)

        activity_row = QHBoxLayout()
        refresh_button = make_button("Refresh activity")
        refresh_button.clicked.connect(self.refresh_audit_log)
        activity_row.addWidget(refresh_button)
        activity_row.addStretch(1)
        activity.body.addLayout(activity_row)
        layout.addWidget(activity)

        about = Card()
        about.body.addWidget(section_label("About"))
        version = QLabel(f"NextStep {__version__}")
        about.body.addWidget(version)
        note = QLabel("Local-first. No account, no telemetry, no cloud sync.")
        note.setProperty("role", "muted")
        about.body.addWidget(note)
        layout.addWidget(about)

        layout.addStretch(1)
        self.refresh_mcp_items()
        self._loading = False
        self._loading_mcp = False
        self._loading_write = False
        self.refresh_audit_log()

    def refresh_mcp_items(self) -> None:
        """Reload the selectable Work Items while keeping saved selections."""
        self._loading_mcp = True
        try:
            policy = self._ctx.mcp_policy.get_policy()
            selected = policy.selected_work_item_ids
            self.mcp_items.clear()
            for work_item in self._ctx.work_items.list_all():
                entry = QListWidgetItem(f"{work_item.title} — {STATUS_LABELS[work_item.status]}")
                entry.setData(Qt.ItemDataRole.UserRole, str(work_item.id))
                entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                entry.setCheckState(
                    Qt.CheckState.Checked if work_item.id in selected else Qt.CheckState.Unchecked
                )
                self.mcp_items.addItem(entry)

            scope = McpScope(self.mcp_scope.currentData())
            self.mcp_items.setVisible(scope is McpScope.SELECTED)
            self.mcp_empty.setVisible(scope is McpScope.SELECTED and self.mcp_items.count() == 0)
        finally:
            self._loading_mcp = False

    def _mcp_scope_selected(self, _index: int) -> None:
        if self._loading_mcp:
            return
        scope = McpScope(self.mcp_scope.currentData())
        self.mcp_items.setVisible(scope is McpScope.SELECTED)
        self.mcp_empty.setVisible(scope is McpScope.SELECTED and self.mcp_items.count() == 0)
        selected = self._checked_work_item_ids() if scope is McpScope.SELECTED else None
        self._ctx.mcp_policy.set_policy(scope, selected)

    def _mcp_client_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.mcp_guides):
            return
        guide = self.mcp_guides[index]
        self.mcp_setup_location.setText(f"Configuration: {guide.location}")
        self.mcp_setup_steps.setText(guide.steps)
        self.mcp_setup_text.setPlainText(guide.configuration)
        self.mcp_setup_text.setVisible(guide.copyable)
        self.copy_mcp_setup_button.setVisible(guide.copyable)
        self.copy_mcp_setup_button.setText("Copy configuration")

    def _copy_mcp_setup(self) -> None:
        configuration = self.mcp_setup_text.toPlainText()
        if not configuration:
            return
        QApplication.clipboard().setText(configuration)
        self.copy_mcp_setup_button.setText("Copied")

    def _mcp_selection_changed(self, _item: QListWidgetItem) -> None:
        if self._loading_mcp:
            return
        scope = McpScope(self.mcp_scope.currentData())
        if scope is not McpScope.SELECTED:
            return
        self._ctx.mcp_policy.set_selected_work_item_ids(self._checked_work_item_ids())

    def _checked_work_item_ids(self) -> list[UUID]:
        ids: list[UUID] = []
        for row in range(self.mcp_items.count()):
            item = self.mcp_items.item(row)
            if item.checkState() is not Qt.CheckState.Checked:
                continue
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                try:
                    ids.append(UUID(value))
                except ValueError:
                    continue
        return ids

    def _update_write_controls(self) -> None:
        enabled = self.mcp_write_enabled.isChecked()
        for check in self.mcp_write_checks.values():
            check.setEnabled(enabled)

    def _mcp_write_enabled_toggled(self, checked: bool) -> None:
        self._update_write_controls()
        if self._loading_write:
            return
        self._ctx.mcp_policy.set_write_enabled(checked)
        self._save_write_operations()

    def _mcp_write_operation_toggled(self, _checked: bool) -> None:
        if self._loading_write:
            return
        self._save_write_operations()

    def _save_write_operations(self) -> None:
        operations = [
            operation for operation, check in self.mcp_write_checks.items() if check.isChecked()
        ]
        self._ctx.mcp_policy.set_allowed_operations(operations)

    def refresh_audit_log(self) -> None:
        """Reload recent MCP activity, newest first."""
        self.mcp_activity.clear()
        try:
            entries = self._ctx.audit.list_recent(50)
        except NextStepError as error:
            self.mcp_activity_empty.setText(str(error))
            self.mcp_activity_empty.setVisible(True)
            return
        for entry in entries:
            self.mcp_activity.addItem(self._audit_text(entry))
        self.mcp_activity_empty.setVisible(not entries)

    def open_data_folder(self) -> None:
        open_path(self._ctx.paths.root)

    def backup(self) -> None:
        self._backup()

    def restore(self) -> None:
        self._restore()

    def export_json(self) -> None:
        self._export_json()

    def sync_theme(self, theme: str) -> None:
        index = self._theme.findData(theme)
        if index >= 0:
            self._theme.blockSignals(True)
            self._theme.setCurrentIndex(index)
            self._theme.blockSignals(False)

    def sync_work_list_view(self, view: str) -> None:
        index = self.work_list_view.findData(view)
        if index >= 0:
            self.work_list_view.blockSignals(True)
            self.work_list_view.setCurrentIndex(index)
            self.work_list_view.blockSignals(False)

    @staticmethod
    def _audit_text(entry: AuditLogEntry) -> str:
        parts = [
            format_local(entry.created_at),
            entry.operation.value.replace("_", " ").capitalize(),
            entry.outcome.value,
        ]
        if entry.changed_fields:
            parts.append(", ".join(entry.changed_fields))
        if entry.error_code:
            parts.append(entry.error_code)
        return "   ·   ".join(parts)

    def _theme_selected(self, _index: int) -> None:
        if self._loading:
            return
        theme = self._theme.currentData()
        if not isinstance(theme, str):
            return
        self._ctx.settings.set_theme(theme)
        self.theme_changed.emit(theme)

    def _work_list_view_selected(self, _index: int) -> None:
        view = self.work_list_view.currentData()
        if not isinstance(view, str):
            return
        self._ctx.settings.set_work_list_view(view)
        self.work_list_view_changed.emit(view)

    def _default_path(self, prefix: str, suffix: str) -> str:
        return str(self._ctx.paths.root / "backups" / f"{prefix}-{_timestamp()}{suffix}")

    def _backup(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Back up NextStep data",
            self._default_path("NextStep-backup", ".zip"),
            _BACKUP_FILTER,
        )
        if not filename:
            return

        try:
            result = self._ctx.portability.backup(Path(filename))
        except NextStepError as error:
            show_error(self, error)
            return

        QMessageBox.information(
            self,
            "Backup complete",
            "NextStep data was backed up to:\n\n"
            f"{result.path}\n\n"
            f"{result.work_item_count} work items, "
            f"{result.checkpoint_count} checkpoints, "
            f"{result.reference_count} references.",
        )

    def _restore(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Restore NextStep backup",
            str(self._ctx.paths.backups_dir),
            _BACKUP_FILTER,
        )
        if not filename:
            return

        answer = QMessageBox.question(
            self,
            "Restore backup",
            "Restoring replaces all current NextStep data.\n\n"
            "A safety backup of the current data will be created first.\n"
            "NextStep will close after a successful restore.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._ctx.portability.restore(Path(filename))
        except RestoreRequiresRestartError as error:
            # The database engine is already closed; continuing would leave the
            # app running without a usable context.
            QMessageBox.critical(
                self,
                "Restart required",
                f"{error.message}\n\nNextStep will close now. "
                "Reopen it before doing anything else.",
            )
            app = QApplication.instance()
            if isinstance(app, QApplication):
                app.quit()
            return
        except NextStepError as error:
            show_error(self, error)
            return

        QMessageBox.information(
            self,
            "Restore complete",
            "NextStep data was restored from:\n\n"
            f"{result.path}\n\n"
            f"Safety backup of the previous data:\n{result.safety_backup}\n\n"
            "NextStep will close now. Reopen it to use the restored data.",
        )
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.quit()

    def _export_json(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export NextStep data",
            self._default_path("NextStep-export", ".json"),
            _EXPORT_FILTER,
        )
        if not filename:
            return

        try:
            result = self._ctx.portability.export_json(Path(filename))
        except NextStepError as error:
            show_error(self, error)
            return

        QMessageBox.information(
            self,
            "Export complete",
            "NextStep data was exported to:\n\n"
            f"{result.path}\n\n"
            f"{result.work_item_count} work items, "
            f"{result.checkpoint_count} checkpoints, "
            f"{result.reference_count} references.",
        )
