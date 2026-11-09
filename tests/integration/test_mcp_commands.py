from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.dto import AddReference, CreateWorkItem
from nextstep.application.mcp_policy import McpScope
from nextstep.domain.enums import AuditOutcome, McpOperation, ReferenceType, WorkItemStatus
from nextstep.domain.errors import AccessDeniedError, NotFoundError, ValidationError

_ALL_WRITE_OPERATIONS = list(McpOperation)


def _enable_write(app_context, *operations: McpOperation) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)
    app_context.mcp_policy.set_write_policy(True, list(operations))


def _last_audit(app_context):
    return app_context.audit.list_recent(1)[0]


def test_write_is_denied_while_mcp_is_off(app_context) -> None:
    with pytest.raises(AccessDeniedError, match="disabled"):
        app_context.mcp_commands.create_work_item(title="Hidden")

    entry = _last_audit(app_context)
    assert entry.operation is McpOperation.CREATE_WORK_ITEM
    assert entry.outcome is AuditOutcome.DENIED
    assert entry.error_code == "access_denied"


def test_write_is_denied_when_change_access_is_off(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)

    with pytest.raises(AccessDeniedError, match="changes are disabled"):
        app_context.mcp_commands.create_work_item(title="Hidden")

    assert _last_audit(app_context).outcome is AuditOutcome.DENIED


def test_write_is_denied_for_ungranted_operation(app_context) -> None:
    _enable_write(app_context, McpOperation.ADD_REFERENCE)

    with pytest.raises(AccessDeniedError, match="not allowed"):
        app_context.mcp_commands.create_work_item(title="Hidden")

    assert _last_audit(app_context).error_code == "access_denied"


def test_create_work_item_audits_and_returns_output(app_context) -> None:
    _enable_write(app_context, McpOperation.CREATE_WORK_ITEM)

    result = app_context.mcp_commands.create_work_item(title="Draft release notes", goal="Publish")

    stored = app_context.work_items.get(result.work_item.id)
    assert stored.title == "Draft release notes"
    assert stored.goal == "Publish"

    entry = _last_audit(app_context)
    assert entry.id == result.audit_id
    assert result.audit_recorded is True
    assert entry.work_item_id == result.work_item.id
    assert entry.outcome is AuditOutcome.SUCCESS
    assert entry.changed_fields == ("title", "goal")


def test_create_work_item_is_shared_in_selected_scope(app_context) -> None:
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [])
    app_context.mcp_policy.set_write_policy(True, [McpOperation.CREATE_WORK_ITEM])

    result = app_context.mcp_commands.create_work_item(title="Shared automatically")

    policy = app_context.mcp_policy.get_policy()
    assert result.work_item.id in policy.selected_work_item_ids


def test_create_work_item_rolls_back_when_selected_scope_cannot_be_updated(
    app_context, monkeypatch
) -> None:
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [])
    app_context.mcp_policy.set_write_policy(True, [McpOperation.CREATE_WORK_ITEM])

    def fail_to_share(_work_item_ids) -> None:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(app_context.mcp_policy, "set_selected_work_item_ids", fail_to_share)

    with pytest.raises(RuntimeError, match="settings unavailable"):
        app_context.mcp_commands.create_work_item(title="Must not remain")

    assert all(item.title != "Must not remain" for item in app_context.work_items.list_all())
    entry = _last_audit(app_context)
    assert entry.outcome is AuditOutcome.ERROR
    assert entry.error_code == "internal_error"


def test_update_work_item_audits_changed_field_names(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Old", goal="Old goal"))
    _enable_write(app_context, McpOperation.UPDATE_WORK_ITEM)

    result = app_context.mcp_commands.update_work_item(item.id, title="New")

    assert result.work_item.title == "New"
    assert app_context.work_items.get(item.id).title == "New"
    entry = _last_audit(app_context)
    assert entry.work_item_id == item.id
    assert entry.changed_fields == ("title",)


def test_update_work_item_requires_a_change(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    _enable_write(app_context, McpOperation.UPDATE_WORK_ITEM)

    with pytest.raises(ValidationError):
        app_context.mcp_commands.update_work_item(item.id)

    entry = _last_audit(app_context)
    assert entry.outcome is AuditOutcome.ERROR
    assert entry.error_code == "validation_error"


def test_update_work_item_denies_unshared_item(app_context) -> None:
    shared = app_context.work_items.create(CreateWorkItem(title="Shared"))
    other = app_context.work_items.create(CreateWorkItem(title="Other"))
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [shared.id])
    app_context.mcp_policy.set_write_policy(True, [McpOperation.UPDATE_WORK_ITEM])

    with pytest.raises(AccessDeniedError, match="not shared"):
        app_context.mcp_commands.update_work_item(other.id, title="Nope")


def test_save_progress_update_appends_checkpoint_without_changing_status(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    app_context.work_items.change_status(item.id, WorkItemStatus.PAUSED)
    _enable_write(app_context, McpOperation.SAVE_PROGRESS_UPDATE)

    result = app_context.mcp_commands.save_progress_update(
        item.id,
        stopped_at="Wiring the form",
        next_actions="Add validation",
        completed_work="Built the form",
    )

    assert result.checkpoint.work_item_id == item.id
    assert app_context.work_items.get(item.id).status is WorkItemStatus.PAUSED
    entry = _last_audit(app_context)
    assert entry.operation is McpOperation.SAVE_PROGRESS_UPDATE
    assert entry.changed_fields == (
        "stopped_at",
        "next_actions",
        "completed_work",
    )


def test_save_progress_update_rejects_finished_work(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Done"))
    app_context.work_items.change_status(item.id, WorkItemStatus.COMPLETED)
    _enable_write(app_context, McpOperation.SAVE_PROGRESS_UPDATE)

    with pytest.raises(ValidationError, match="resume"):
        app_context.mcp_commands.save_progress_update(item.id, stopped_at="x", next_actions="y")

    assert _last_audit(app_context).outcome is AuditOutcome.ERROR


def test_change_status_resumes_paused_work(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    app_context.work_items.change_status(item.id, WorkItemStatus.PAUSED)
    _enable_write(app_context, McpOperation.CHANGE_WORK_ITEM_STATUS)

    result = app_context.mcp_commands.change_work_item_status(item.id, WorkItemStatus.ACTIVE)

    assert result.work_item.status is WorkItemStatus.ACTIVE
    assert app_context.work_items.get(item.id).status is WorkItemStatus.ACTIVE


def test_change_status_cannot_resume_finished_work(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    app_context.work_items.change_status(item.id, WorkItemStatus.COMPLETED)
    _enable_write(app_context, McpOperation.CHANGE_WORK_ITEM_STATUS)

    with pytest.raises(ValidationError, match="resume completed"):
        app_context.mcp_commands.change_work_item_status(item.id, WorkItemStatus.ACTIVE)

    assert app_context.work_items.get(item.id).status is WorkItemStatus.COMPLETED


def test_reference_lifecycle_is_audited(app_context, clock) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Task"))
    _enable_write(
        app_context,
        McpOperation.ADD_REFERENCE,
        McpOperation.UPDATE_REFERENCE,
        McpOperation.DELETE_REFERENCE,
    )

    added = app_context.mcp_commands.add_reference(
        item.id,
        reference_type=ReferenceType.URL,
        label="Docs",
        target="https://example.com/docs",
    )
    clock.advance(minutes=1)
    updated = app_context.mcp_commands.update_reference(added.reference.id, label="Handbook")
    clock.advance(minutes=1)
    deleted = app_context.mcp_commands.delete_reference(updated.reference.id)

    assert updated.reference.label == "Handbook"
    assert deleted.deleted is True
    assert app_context.references.list_for_work_item(item.id) == []

    entries = app_context.audit.list_recent(3)
    assert [entry.operation for entry in entries] == [
        McpOperation.DELETE_REFERENCE,
        McpOperation.UPDATE_REFERENCE,
        McpOperation.ADD_REFERENCE,
    ]
    assert all(entry.outcome is AuditOutcome.SUCCESS for entry in entries)


def test_reference_denied_for_unshared_work_item(app_context) -> None:
    shared = app_context.work_items.create(CreateWorkItem(title="Shared"))
    other = app_context.work_items.create(CreateWorkItem(title="Other"))
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [shared.id])
    app_context.mcp_policy.set_write_policy(True, [McpOperation.ADD_REFERENCE])

    with pytest.raises(AccessDeniedError, match="not shared"):
        app_context.mcp_commands.add_reference(
            other.id,
            reference_type=ReferenceType.URL,
            label="Docs",
            target="https://example.com",
        )


def test_missing_reference_is_audited_as_not_found(app_context) -> None:
    _enable_write(app_context, McpOperation.DELETE_REFERENCE)

    with pytest.raises(NotFoundError):
        app_context.mcp_commands.delete_reference(uuid4())

    entry = _last_audit(app_context)
    assert entry.outcome is AuditOutcome.ERROR
    assert entry.error_code == "not_found"


def test_selected_scope_does_not_reveal_whether_reference_exists(app_context) -> None:
    shared = app_context.work_items.create(CreateWorkItem(title="Shared"))
    hidden = app_context.work_items.create(CreateWorkItem(title="Hidden"))
    hidden_reference = app_context.references.add(
        AddReference(
            work_item_id=hidden.id,
            type=ReferenceType.URL,
            label="Hidden docs",
            target="https://example.com/hidden",
        )
    )
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [shared.id])
    app_context.mcp_policy.set_write_policy(True, [McpOperation.DELETE_REFERENCE])

    for reference_id in (hidden_reference.id, uuid4()):
        with pytest.raises(AccessDeniedError, match="not available"):
            app_context.mcp_commands.delete_reference(reference_id)


def test_successful_write_reports_when_audit_cannot_be_recorded(app_context, monkeypatch) -> None:
    _enable_write(app_context, McpOperation.CREATE_WORK_ITEM)

    def fail_to_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(app_context.audit, "record", fail_to_audit)

    result = app_context.mcp_commands.create_work_item(title="Created without audit")

    assert result.audit_id is None
    assert result.audit_recorded is False
    assert app_context.work_items.get(result.work_item.id).title == "Created without audit"


def test_audit_log_never_contains_user_content(app_context) -> None:
    _enable_write(app_context, *_ALL_WRITE_OPERATIONS)
    item = app_context.mcp_commands.create_work_item(
        title="Secret title", goal="Secret goal"
    ).work_item
    app_context.mcp_commands.update_work_item(item.id, goal="Another secret goal")
    app_context.mcp_commands.save_progress_update(
        item.id,
        stopped_at="Secret stopping point",
        next_actions="Secret next action",
        context_summary="Secret context",
    )
    app_context.mcp_commands.add_reference(
        item.id,
        reference_type=ReferenceType.URL,
        label="Secret label",
        target="https://example.com/secret-path",
    )

    rendered = "\n".join(
        f"{entry.tool_name} {entry.operation.value} {entry.changed_fields} {entry.error_code or ''}"
        for entry in app_context.audit.list_recent(50)
    )

    for secret in (
        "Secret title",
        "Secret goal",
        "Another secret goal",
        "Secret stopping point",
        "Secret next action",
        "Secret context",
        "Secret label",
        "secret-path",
    ):
        assert secret not in rendered
