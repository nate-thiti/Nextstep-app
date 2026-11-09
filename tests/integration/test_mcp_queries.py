from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.application.mcp_policy import McpScope
from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.domain.errors import AccessDeniedError, NotFoundError, ValidationError


def _seed(app_context):
    first = app_context.work_items.create(
        CreateWorkItem(title="Alpha", goal="Ship authentication", group_name="Work")
    )
    second = app_context.work_items.create(CreateWorkItem(title="Beta", goal="Write docs"))
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=first.id,
            stopped_at="Authentication flow",
            next_actions="Write login tests",
            completed_work="Implemented login form",
            blockers="Waiting for API key",
        )
    )
    app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=second.id,
            stopped_at="Documentation outline",
            next_actions="Publish the guide",
            context_summary="Beta-only secret context",
        )
    )
    return first, second


def test_list_is_denied_while_mcp_is_off(app_context) -> None:
    with pytest.raises(AccessDeniedError):
        app_context.mcp_queries.list_work_items()


def test_list_returns_shared_work_items(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)

    result = app_context.mcp_queries.list_work_items()

    assert result.total == 2
    assert {item.work_item.id for item in result.items} == {first.id, second.id}
    assert result.has_more is False
    alpha = next(item for item in result.items if item.work_item.id == first.id)
    assert alpha.work_item.goal == "Ship authentication"
    assert alpha.work_item.group == "Work"
    assert alpha.latest_checkpoint_id is not None


def test_list_filters_by_status_and_search(app_context) -> None:
    first, second = _seed(app_context)
    app_context.work_items.change_status(second.id, WorkItemStatus.PAUSED)
    app_context.mcp_policy.set_scope(McpScope.ALL)

    paused = app_context.mcp_queries.list_work_items(status=WorkItemStatus.PAUSED)
    found = app_context.mcp_queries.list_work_items(search="authentication")
    grouped = app_context.mcp_queries.list_work_items(group_name="Work")

    assert [item.work_item.id for item in paused.items] == [second.id]
    assert [item.work_item.id for item in found.items] == [first.id]
    assert [item.work_item.id for item in grouped.items] == [first.id]


def test_list_paginates_and_reports_has_more(app_context) -> None:
    for index in range(5):
        app_context.work_items.create(CreateWorkItem(title=f"Task {index}"))
    app_context.mcp_policy.set_scope(McpScope.ALL)

    first_page = app_context.mcp_queries.list_work_items(limit=2, offset=0)
    last_page = app_context.mcp_queries.list_work_items(limit=2, offset=4)

    assert first_page.total == 5
    assert len(first_page.items) == 2
    assert first_page.has_more is True
    assert len(last_page.items) == 1
    assert last_page.has_more is False


def test_selected_scope_hides_other_work_items(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [first.id])

    result = app_context.mcp_queries.list_work_items()

    assert [item.work_item.id for item in result.items] == [first.id]
    with pytest.raises(AccessDeniedError):
        app_context.mcp_queries.get_work_context(second.id)


def test_get_work_context_includes_latest_checkpoint_and_references(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Alpha", goal="Ship"))
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Repository",
            target="https://example.com/repo",
        )
    )
    checkpoint = app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="Halfway",
            next_actions="Continue",
            context_summary="Useful summary",
        )
    )
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=checkpoint.id,
            type=ReferenceType.URL,
            label="Latest docs",
            target="https://example.com/docs",
        )
    )
    app_context.mcp_policy.set_scope(McpScope.ALL)

    result = app_context.mcp_queries.get_work_context(item.id)

    assert result.work_item.title == "Alpha"
    assert result.latest_checkpoint is not None
    assert result.latest_checkpoint.id == checkpoint.id
    assert result.latest_checkpoint.context_summary == "Useful summary"
    assert [reference.label for reference in result.references] == ["Repository", "Latest docs"]


def test_latest_checkpoint_can_be_missing(app_context) -> None:
    item = app_context.work_items.create(CreateWorkItem(title="Empty"))
    app_context.mcp_policy.set_scope(McpScope.ALL)

    result = app_context.mcp_queries.get_latest_checkpoint(item.id)

    assert result.work_item.id == item.id
    assert result.checkpoint is None


def test_search_checkpoints_finds_text_case_insensitively(app_context) -> None:
    first, _ = _seed(app_context)
    app_context.mcp_policy.set_scope(McpScope.ALL)

    result = app_context.mcp_queries.search_checkpoints("IMPLEMENTED LOGIN")

    assert result.total == 1
    assert result.items[0].work_item_id == first.id
    assert result.items[0].work_item_title == "Alpha"
    assert result.items[0].checkpoint.completed_work == "Implemented login form"


def test_search_checkpoints_respects_selected_scope(app_context) -> None:
    first, second = _seed(app_context)
    app_context.mcp_policy.set_policy(McpScope.SELECTED, [first.id])

    allowed = app_context.mcp_queries.search_checkpoints("login")
    hidden = app_context.mcp_queries.search_checkpoints("beta-only")

    assert [hit.work_item_id for hit in allowed.items] == [first.id]
    assert hidden.total == 0
    with pytest.raises(AccessDeniedError):
        app_context.mcp_queries.search_checkpoints("beta-only", work_item_id=second.id)


def test_search_checkpoints_rejects_blank_query(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)

    with pytest.raises(ValidationError):
        app_context.mcp_queries.search_checkpoints("   ")


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (10, -1)])
def test_page_bounds_are_validated(app_context, limit: int, offset: int) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)

    with pytest.raises(ValidationError):
        app_context.mcp_queries.list_work_items(limit=limit, offset=offset)


def test_missing_work_item_is_reported(app_context) -> None:
    app_context.mcp_policy.set_scope(McpScope.ALL)

    with pytest.raises(NotFoundError):
        app_context.mcp_queries.get_work_context(uuid4())
