"""Local MCP access policy.

MCP is off by default. When enabled it can expose every Work Item or only the
ones the user explicitly selected. The policy lives in ``app_settings`` so the
desktop app and the MCP server always read the same state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from nextstep.application.settings import SettingsService
from nextstep.domain.enums import McpOperation
from nextstep.domain.errors import ValidationError

MCP_ENABLED_KEY = "mcp.enabled"
MCP_SCOPE_KEY = "mcp.scope"
MCP_SELECTED_WORK_ITEMS_KEY = "mcp.selected_work_items"
MCP_WRITE_ENABLED_KEY = "mcp.write_enabled"
MCP_WRITE_OPERATIONS_KEY = "mcp.write_operations"

DEFAULT_SCOPE = "selected"


class McpScope(StrEnum):
    """How much local context the MCP server may read."""

    DISABLED = "disabled"
    SELECTED = "selected"
    ALL = "all"


@dataclass(frozen=True)
class McpAccessPolicy:
    scope: McpScope
    selected_work_item_ids: frozenset[UUID] = frozenset()

    @property
    def enabled(self) -> bool:
        return self.scope is not McpScope.DISABLED

    def allows(self, work_item_id: UUID) -> bool:
        if self.scope is McpScope.ALL:
            return True
        if self.scope is McpScope.SELECTED:
            return work_item_id in self.selected_work_item_ids
        return False

    def allowed_work_item_ids(self) -> list[UUID] | None:
        """``None`` means every Work Item; a list means only those IDs."""
        if self.scope is McpScope.ALL:
            return None
        return sorted(self.selected_work_item_ids, key=str)


@dataclass(frozen=True)
class McpWritePolicy:
    """Capabilities granted to MCP write tools on top of the read scope."""

    enabled: bool
    operations: frozenset[McpOperation]
    access: McpAccessPolicy

    def allows(self, operation: McpOperation, work_item_id: UUID | None = None) -> bool:
        if not self.access.enabled or not self.enabled:
            return False
        if operation not in self.operations:
            return False
        if work_item_id is None:
            return True
        return self.access.allows(work_item_id)


class McpPolicyService:
    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    def get_policy(self) -> McpAccessPolicy:
        enabled = self._settings.get(MCP_ENABLED_KEY, False) is True
        raw_scope = self._settings.get(MCP_SCOPE_KEY, DEFAULT_SCOPE)
        try:
            stored_scope = (
                McpScope(raw_scope) if isinstance(raw_scope, str) else McpScope(DEFAULT_SCOPE)
            )
        except ValueError:
            stored_scope = McpScope(DEFAULT_SCOPE)

        scope = stored_scope if enabled else McpScope.DISABLED

        return McpAccessPolicy(
            scope=scope,
            selected_work_item_ids=frozenset(self._selected_ids()),
        )

    def set_scope(self, scope: McpScope) -> None:
        if not isinstance(scope, McpScope):
            raise ValidationError("mcp.scope", "must be disabled, selected or all")
        self._settings.set(MCP_ENABLED_KEY, scope is not McpScope.DISABLED)
        self._settings.set(MCP_SCOPE_KEY, scope.value)

    def set_selected_work_item_ids(self, work_item_ids: list[UUID]) -> None:
        unique = sorted({str(work_item_id) for work_item_id in work_item_ids})
        self._settings.set(MCP_SELECTED_WORK_ITEMS_KEY, unique)

    def set_policy(self, scope: McpScope, work_item_ids: list[UUID] | None = None) -> None:
        if work_item_ids is not None:
            self.set_selected_work_item_ids(work_item_ids)
        self.set_scope(scope)

    def get_write_policy(self) -> McpWritePolicy:
        enabled = self._settings.get(MCP_WRITE_ENABLED_KEY, False) is True
        return McpWritePolicy(
            enabled=enabled,
            operations=frozenset(self._allowed_operations()),
            access=self.get_policy(),
        )

    def set_write_enabled(self, enabled: bool) -> None:
        self._settings.set(MCP_WRITE_ENABLED_KEY, bool(enabled))

    def set_allowed_operations(self, operations: list[McpOperation]) -> None:
        for operation in operations:
            if not isinstance(operation, McpOperation):
                raise ValidationError("mcp.write_operations", "contains an unknown operation")
        unique = sorted({operation.value for operation in operations})
        self._settings.set(MCP_WRITE_OPERATIONS_KEY, unique)

    def set_write_policy(self, enabled: bool, operations: list[McpOperation]) -> None:
        self.set_allowed_operations(operations)
        self.set_write_enabled(enabled)

    def _allowed_operations(self) -> list[McpOperation]:
        raw = self._settings.get(MCP_WRITE_OPERATIONS_KEY, [])
        if not isinstance(raw, list):
            return []
        operations: list[McpOperation] = []
        for value in raw:
            if not isinstance(value, str):
                continue
            try:
                operations.append(McpOperation(value))
            except ValueError:
                continue
        return operations

    def _selected_ids(self) -> list[UUID]:
        raw = self._settings.get(MCP_SELECTED_WORK_ITEMS_KEY, [])
        if not isinstance(raw, list):
            return []
        ids: list[UUID] = []
        for value in raw:
            if not isinstance(value, str):
                continue
            try:
                ids.append(UUID(value))
            except ValueError:
                continue
        return ids
