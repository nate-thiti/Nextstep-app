from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult

from nextstep.application.dto import CreateWorkItem, SaveCheckpoint
from nextstep.application.mcp_policy import McpScope
from nextstep.domain.enums import McpOperation, ReferenceType
from nextstep.infrastructure.paths import DataPaths
from nextstep.mcp_server import main as main_module
from nextstep.mcp_server.server import TOOL_NAMES, build_server


def _call(server, name: str, arguments: dict[str, Any]) -> CallToolResult:
    result = asyncio.run(server.call_tool(name, arguments))
    assert isinstance(result, CallToolResult)
    return result


def _structured(server, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = _call(server, name, arguments)
    assert isinstance(result, CallToolResult)
    assert result.structured_content is not None
    return result.structured_content


def _seed(app_context):
    first = app_context.work_items.create(CreateWorkItem(title="Alpha", goal="Ship authentication"))
    second = app_context.work_items.create(CreateWorkItem(title="Beta"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=first.id,
            stopped_at="Authentication flow",
            next_actions="Write login tests",
            completed_work="Implemented login form",
        )
    )
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=second.id,
            stopped_at="Docs",
            next_actions="Publish",
            context_summary="Beta-only context",
        )
    )
    return first, second


def test_server_exposes_read_and_write_tools(app_context) -> None:
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == list(TOOL_NAMES)
    assert len(tools) == 11
    assert "delete_work_item" not in {tool.name for tool in tools}


def test_tools_are_denied_while_mcp_is_off(app_context) -> None:
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="disabled"):
        _call(server, "list_work_items", {})


def test_list_work_items_returns_structured_output(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    result = _structured(server, "list_work_items", {"limit": 10})

    assert result["total"] == 2
    ids = {item["work_item"]["id"] for item in result["items"]}
    assert ids == {str(first.id), str(second.id)}


def test_list_work_items_validates_status_and_page(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="Unknown status"):
        _call(server, "list_work_items", {"status": "sleeping"})
    with pytest.raises(ToolError, match="limit"):
        _call(server, "list_work_items", {"limit": 0})


def test_selected_scope_denies_other_work_items(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [first.id])
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="not shared"):
        _call(server, "get_work_context", {"work_item_id": str(second.id)})


def test_get_work_context_and_latest_checkpoint(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    context = _call(server, "get_work_context", {"work_item_id": str(first.id)})
    latest = _call(server, "get_latest_checkpoint", {"work_item_id": str(first.id)})

    assert context.structured_content is not None
    assert context.structured_content["work_item"]["title"] == "Alpha"
    assert context.structured_content["latest_checkpoint"]["completed_work"] == (
        "Implemented login form"
    )
    assert latest.structured_content is not None
    assert latest.structured_content["checkpoint"]["stopped_at"] == "Authentication flow"


def test_search_checkpoints_returns_hits(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    result = _call(server, "search_checkpoints", {"query": "login"})

    assert result.structured_content is not None
    assert result.structured_content["total"] == 1
    assert result.structured_content["items"][0]["work_item_id"] == str(first.id)


def test_search_checkpoints_does_not_leak_unshared_items(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [first.id])
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    result = _call(server, "search_checkpoints", {"query": "beta-only"})

    assert result.structured_content is not None
    assert result.structured_content["total"] == 0
    with pytest.raises(ToolError, match="not shared"):
        _call(
            server,
            "search_checkpoints",
            {"query": "beta-only", "work_item_id": str(second.id)},
        )


def test_missing_work_item_becomes_tool_error(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="not found"):
        _call(server, "get_latest_checkpoint", {"work_item_id": str(uuid4())})


def test_write_tools_are_denied_until_enabled(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="changes are disabled"):
        _call(server, "create_work_item", {"title": "Blocked"})

    app_context.mcp_policy.set_write_policy(True, [McpOperation.CREATE_WORK_ITEM])
    result = _structured(server, "create_work_item", {"title": "Allowed", "goal": "Ship"})

    assert result["work_item"]["title"] == "Allowed"
    assert result["work_item"]["goal"] == "Ship"
    assert result["audit_recorded"] is True
    assert result["audit_id"] is not None


def test_update_work_item_through_server(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    app_context.mcp_policy.set_write_policy(True, [McpOperation.UPDATE_WORK_ITEM])
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    result = _structured(
        server,
        "update_work_item",
        {"work_item_id": str(first.id), "title": "Alpha v2"},
    )

    assert result["work_item"]["title"] == "Alpha v2"


def test_add_and_delete_reference_through_server(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    app_context.mcp_policy.set_write_policy(
        True, [McpOperation.ADD_REFERENCE, McpOperation.DELETE_REFERENCE]
    )
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    added = _structured(
        server,
        "add_reference",
        {
            "work_item_id": str(first.id),
            "type": ReferenceType.URL.value,
            "label": "Docs",
            "target": "https://example.com/docs",
        },
    )
    reference_id = added["reference"]["id"]

    deleted = _structured(server, "delete_reference", {"reference_id": reference_id})

    assert deleted["deleted"] is True
    assert deleted["reference_id"] == reference_id


def test_invalid_reference_type_becomes_tool_error(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)
    app_context.mcp_policy.set_write_policy(True, [McpOperation.ADD_REFERENCE])
    server = build_server(app_context.mcp_queries, app_context.mcp_commands)

    with pytest.raises(ToolError, match="Unknown reference type"):
        _call(
            server,
            "add_reference",
            {
                "work_item_id": str(first.id),
                "type": "spreadsheet",
                "label": "Nope",
                "target": "https://example.com",
            },
        )


def test_entry_point_runs_stdio_and_closes_context(monkeypatch, tmp_path) -> None:
    paths = DataPaths.resolve(tmp_path / "mcp-data")
    transports: list[str] = []

    class FakeContext:
        mcp_queries = object()
        mcp_commands = object()
        closed = False

        def close(self) -> None:
            self.closed = True

    class FakeServer:
        def run(self, transport: str) -> None:
            transports.append(transport)

    context = FakeContext()
    monkeypatch.setattr(main_module.DataPaths, "resolve", lambda: paths)
    monkeypatch.setattr(main_module, "configure_logging", lambda _path: None)
    monkeypatch.setattr(main_module, "build_context", lambda _paths: context)
    monkeypatch.setattr(main_module, "build_server", lambda _queries, _commands: FakeServer())

    assert main_module.main() == 0
    assert transports == ["stdio"]
    assert context.closed is True
