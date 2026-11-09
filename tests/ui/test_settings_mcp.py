from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from nextstep.application.dto import CreateWorkItem
from nextstep.application.mcp_policy import McpScope
from nextstep.desktop.settings_view import SettingsView
from nextstep.domain.enums import AuditOutcome, McpOperation


def test_mcp_defaults_to_off(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.mcp_scope.currentData() == McpScope.DISABLED.value
    assert view.mcp_scope.cursor().shape() is Qt.CursorShape.PointingHandCursor
    assert view.mcp_scope.view().cursor().shape() is Qt.CursorShape.PointingHandCursor
    assert app_context.mcp_policy.get_policy().scope is McpScope.DISABLED
    assert view.mcp_items.isHidden()


def test_mcp_client_guide_switches_format_and_copies(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    vscode_index = view.mcp_client.findData("vscode")
    view.mcp_client.setCurrentIndex(vscode_index)

    assert '"servers"' in view.mcp_setup_text.toPlainText()
    assert '"type": "stdio"' in view.mcp_setup_text.toPlainText()
    view.copy_mcp_setup_button.click()
    assert QApplication.clipboard().text() == view.mcp_setup_text.toPlainText()
    assert view.copy_mcp_setup_button.text() == "Copied"

    web_index = view.mcp_client.findData("web_clients")
    view.mcp_client.setCurrentIndex(web_index)
    assert view.mcp_setup_text.isHidden()
    assert view.copy_mcp_setup_button.isHidden()


def test_selecting_all_enables_mcp_for_every_item(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    view.mcp_scope.setCurrentIndex(view.mcp_scope.findData(McpScope.ALL.value))

    policy = app_context.mcp_policy.get_policy()
    assert policy.scope is McpScope.ALL
    assert policy.enabled is True


def test_selected_scope_saves_checked_work_items(qtbot, app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    view.refresh_mcp_items()

    view.mcp_scope.setCurrentIndex(view.mcp_scope.findData(McpScope.SELECTED.value))
    entry = view.mcp_items.item(0)
    entry.setCheckState(Qt.CheckState.Checked)

    policy = app_context.mcp_policy.get_policy()
    assert policy.scope is McpScope.SELECTED
    assert policy.selected_work_item_ids == frozenset({item.id})
    assert view.mcp_items.isHidden() is False


def test_saved_selection_is_restored_on_open(qtbot, app_context) -> None:
    first = app_context.work_items.create(CreateWorkItem(title="First"))
    app_context.work_items.create(CreateWorkItem(title="Second"))
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [first.id])

    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.mcp_scope.currentData() == McpScope.SELECTED.value
    checked = [
        view.mcp_items.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(view.mcp_items.count())
        if view.mcp_items.item(row).checkState() is Qt.CheckState.Checked
    ]
    assert checked == [str(first.id)]


def test_refresh_picks_up_new_work_items(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    assert view.mcp_items.count() == 0

    app_context.work_items.create(CreateWorkItem(title="New task"))
    view.refresh_mcp_items()

    assert view.mcp_items.count() == 1


def test_selected_scope_shows_empty_hint_without_items(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    view.mcp_scope.setCurrentIndex(view.mcp_scope.findData(McpScope.SELECTED.value))

    assert view.mcp_empty.isHidden() is False


def test_write_access_defaults_to_off(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.mcp_write_enabled.isChecked() is False
    assert view.mcp_permissions.property("role") == "permissions"
    assert all(check.isChecked() is False for check in view.mcp_write_checks.values())
    assert all(check.isEnabled() is False for check in view.mcp_write_checks.values())
    assert app_context.mcp_policy.get_write_policy().enabled is False


def test_enabling_write_access_enables_operations(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    view.mcp_write_enabled.setChecked(True)

    assert all(check.isEnabled() for check in view.mcp_write_checks.values())
    assert app_context.mcp_policy.get_write_policy().enabled is True


def test_checked_operations_are_saved(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    view.mcp_write_enabled.setChecked(True)

    view.mcp_write_checks[McpOperation.ADD_REFERENCE].setChecked(True)
    view.mcp_write_checks[McpOperation.UPDATE_WORK_ITEM].setChecked(True)

    operations = app_context.mcp_policy.get_write_policy().operations
    assert operations == frozenset({McpOperation.ADD_REFERENCE, McpOperation.UPDATE_WORK_ITEM})


def test_saved_write_policy_is_restored_on_open(qtbot, app_context) -> None:
    app_context.mcp_policy.set_write_policy(True, [McpOperation.DELETE_REFERENCE])

    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.mcp_write_enabled.isChecked() is True
    assert view.mcp_write_checks[McpOperation.DELETE_REFERENCE].isChecked() is True
    assert view.mcp_write_checks[McpOperation.CREATE_WORK_ITEM].isChecked() is False


def test_activity_lists_recent_audit_entries(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    assert view.mcp_activity.count() == 0
    assert view.mcp_activity_empty.isHidden() is False

    app_context.audit.record(
        tool_name="create_work_item",
        operation=McpOperation.CREATE_WORK_ITEM,
        outcome=AuditOutcome.SUCCESS,
        changed_fields=("title",),
    )
    view.refresh_audit_log()

    assert view.mcp_activity.count() == 1
    assert view.mcp_activity_empty.isHidden() is True
    text = view.mcp_activity.item(0).text()
    assert "Create work item" in text
    assert "success" in text
    assert "title" in text
