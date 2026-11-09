from __future__ import annotations

from uuid import uuid4

import pytest

from nextstep.application.audit import AuditService
from nextstep.domain.enums import AuditOutcome, McpOperation
from nextstep.domain.errors import ValidationError


def _audit(database, clock) -> AuditService:
    return AuditService(database.uow, clock)


def test_record_persists_metadata_only(database, clock) -> None:
    service = _audit(database, clock)
    work_item_id = uuid4()

    entry = service.record(
        tool_name="update_work_item",
        operation=McpOperation.UPDATE_WORK_ITEM,
        outcome=AuditOutcome.SUCCESS,
        work_item_id=work_item_id,
        changed_fields=("title", "goal"),
    )

    recent = service.list_recent(10)
    assert [stored.id for stored in recent] == [entry.id]
    stored = recent[0]
    assert stored.actor == "mcp"
    assert stored.tool_name == "update_work_item"
    assert stored.operation is McpOperation.UPDATE_WORK_ITEM
    assert stored.outcome is AuditOutcome.SUCCESS
    assert stored.work_item_id == work_item_id
    assert stored.changed_fields == ("title", "goal")
    assert stored.error_code is None


def test_list_recent_orders_newest_first(database, clock) -> None:
    service = _audit(database, clock)
    first = service.record(
        tool_name="create_work_item",
        operation=McpOperation.CREATE_WORK_ITEM,
        outcome=AuditOutcome.SUCCESS,
    )
    clock.advance(minutes=1)
    second = service.record(
        tool_name="delete_reference",
        operation=McpOperation.DELETE_REFERENCE,
        outcome=AuditOutcome.ERROR,
        error_code="not_found",
    )

    recent = service.list_recent(10)

    assert [entry.id for entry in recent] == [second.id, first.id]
    assert recent[0].error_code == "not_found"


def test_count_reflects_stored_entries(database, clock) -> None:
    service = _audit(database, clock)
    assert service.count() == 0

    service.record(
        tool_name="create_work_item",
        operation=McpOperation.CREATE_WORK_ITEM,
        outcome=AuditOutcome.SUCCESS,
    )

    assert service.count() == 1


@pytest.mark.parametrize("limit", [0, -1, 501])
def test_list_recent_rejects_out_of_range_limit(database, clock, limit: int) -> None:
    service = _audit(database, clock)

    with pytest.raises(ValidationError):
        service.list_recent(limit)
