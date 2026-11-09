from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.mcp_policy import (
    MCP_ENABLED_KEY,
    MCP_SCOPE_KEY,
    MCP_SELECTED_WORK_ITEMS_KEY,
    MCP_WRITE_ENABLED_KEY,
    MCP_WRITE_OPERATIONS_KEY,
    McpPolicyService,
    McpScope,
)
from nextstep.application.settings import SettingsService
from nextstep.domain.enums import McpOperation
from nextstep.domain.errors import ValidationError


def _policy(database) -> McpPolicyService:
    return McpPolicyService(SettingsService(database.uow))


def test_mcp_is_disabled_by_default(database) -> None:
    policy = _policy(database).get_policy()

    assert policy.scope is McpScope.DISABLED
    assert policy.enabled is False
    assert policy.allowed_work_item_ids() == []
    assert policy.allows(uuid4()) is False


def test_all_scope_exposes_every_work_item(database) -> None:
    service = _policy(database)
    service.set_scope(McpScope.ALL)

    policy = service.get_policy()

    assert policy.enabled is True
    assert policy.scope is McpScope.ALL
    assert policy.allowed_work_item_ids() is None
    assert policy.allows(uuid4()) is True


def test_selected_scope_exposes_only_selected_work_items(database) -> None:
    service = _policy(database)
    selected = uuid4()
    other = uuid4()

    service.set_policy(McpScope.SELECTED, [selected])

    policy = service.get_policy()
    assert policy.scope is McpScope.SELECTED
    assert policy.allows(selected) is True
    assert policy.allows(other) is False
    assert policy.allowed_work_item_ids() == [selected]


def test_selection_is_deduplicated_and_kept_when_switching(database) -> None:
    service = _policy(database)
    selected = uuid4()

    service.set_policy(McpScope.SELECTED, [selected, selected])
    service.set_scope(McpScope.ALL)
    service.set_scope(McpScope.SELECTED)

    assert service.get_policy().selected_work_item_ids == frozenset({selected})


def test_disabling_mcp_keeps_the_saved_selection(database) -> None:
    service = _policy(database)
    selected = uuid4()
    service.set_policy(McpScope.SELECTED, [selected])

    service.set_scope(McpScope.DISABLED)

    policy = service.get_policy()
    assert policy.scope is McpScope.DISABLED
    assert policy.selected_work_item_ids == frozenset({selected})


def test_malformed_settings_fall_back_to_selected(database) -> None:
    settings = SettingsService(database.uow)
    valid = uuid4()
    settings.set(MCP_ENABLED_KEY, True)
    settings.set(MCP_SCOPE_KEY, "bogus")
    settings.set(MCP_SELECTED_WORK_ITEMS_KEY, ["not-a-uuid", 42, str(valid)])

    policy = McpPolicyService(settings).get_policy()

    assert policy.scope is McpScope.SELECTED
    assert policy.selected_work_item_ids == frozenset({valid})


def test_invalid_scope_is_rejected(database) -> None:
    service = _policy(database)

    with pytest.raises(ValidationError):
        service.set_scope("all")  # type: ignore[arg-type]


def test_write_access_is_disabled_by_default(database) -> None:
    service = _policy(database)
    service.set_scope(McpScope.ALL)

    write = service.get_write_policy()

    assert write.enabled is False
    assert write.operations == frozenset()
    assert write.allows(McpOperation.CREATE_WORK_ITEM) is False


def test_write_policy_requires_read_access(database) -> None:
    service = _policy(database)
    service.set_write_policy(True, [McpOperation.CREATE_WORK_ITEM])

    write = service.get_write_policy()

    assert write.enabled is True
    assert write.access.enabled is False
    assert write.allows(McpOperation.CREATE_WORK_ITEM) is False


def test_write_policy_grants_only_selected_operations(database) -> None:
    service = _policy(database)
    service.set_scope(McpScope.ALL)
    service.set_write_policy(True, [McpOperation.CREATE_WORK_ITEM, McpOperation.ADD_REFERENCE])

    write = service.get_write_policy()

    assert write.operations == frozenset(
        {McpOperation.CREATE_WORK_ITEM, McpOperation.ADD_REFERENCE}
    )
    assert write.allows(McpOperation.CREATE_WORK_ITEM) is True
    assert write.allows(McpOperation.DELETE_REFERENCE) is False


def test_write_policy_respects_selected_scope(database) -> None:
    service = _policy(database)
    shared = uuid4()
    other = uuid4()
    service.set_policy(McpScope.SELECTED, [shared])
    service.set_write_policy(True, [McpOperation.UPDATE_WORK_ITEM])

    write = service.get_write_policy()

    assert write.allows(McpOperation.UPDATE_WORK_ITEM, shared) is True
    assert write.allows(McpOperation.UPDATE_WORK_ITEM, other) is False


def test_allowed_operations_are_deduplicated(database) -> None:
    service = _policy(database)

    service.set_allowed_operations([McpOperation.ADD_REFERENCE, McpOperation.ADD_REFERENCE])

    settings = SettingsService(database.uow)
    assert settings.get(MCP_WRITE_OPERATIONS_KEY) == [McpOperation.ADD_REFERENCE.value]


def test_unknown_operation_is_rejected(database) -> None:
    service = _policy(database)

    with pytest.raises(ValidationError):
        service.set_allowed_operations(["delete_everything"])  # type: ignore[list-item]


def test_malformed_write_settings_are_ignored(database) -> None:
    settings = SettingsService(database.uow)
    settings.set(MCP_ENABLED_KEY, True)
    settings.set(MCP_SCOPE_KEY, McpScope.ALL.value)
    settings.set(MCP_WRITE_ENABLED_KEY, True)
    settings.set(MCP_WRITE_OPERATIONS_KEY, ["bogus", 42, McpOperation.ADD_REFERENCE.value])

    write = McpPolicyService(settings).get_write_policy()

    assert write.operations == frozenset({McpOperation.ADD_REFERENCE})
