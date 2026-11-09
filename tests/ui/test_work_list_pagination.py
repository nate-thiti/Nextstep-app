"""BUG-004: the Work List must expose items beyond the first page."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from nextstep.desktop.work_list import WorkListView
from nextstep.domain.entities import WorkItem
from nextstep.domain.enums import WorkItemStatus


def _bulk_create(app_context, count: int) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with app_context.database.uow() as uow:
        for index in range(count):
            uow.work_items.add(
                WorkItem(
                    id=uuid4(),
                    title=f"Task {index:03d}",
                    status=WorkItemStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
        uow.commit()


def test_load_more_reaches_items_past_the_first_page(qtbot, app_context) -> None:
    _bulk_create(app_context, 250)

    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()

    assert view._table.rowCount() == 100
    assert not view._load_more.isHidden()
    assert view._subheading.text() == "Showing 100 of 250 work items"

    view._load_more.click()
    assert view._table.rowCount() == 200
    assert view._subheading.text() == "Showing 200 of 250 work items"

    view._load_more.click()
    assert view._table.rowCount() == 250
    assert view._load_more.isHidden()
    assert view._subheading.text() == "250 work items"


def test_changing_the_search_resets_pagination(qtbot, app_context) -> None:
    _bulk_create(app_context, 150)

    view = WorkListView(app_context)
    qtbot.addWidget(view)
    view.refresh()
    view._load_more.click()
    assert view._table.rowCount() == 150

    view._search.setText("Task 149")
    view.refresh()

    assert view._table.rowCount() == 1
    assert view._load_more.isHidden()
    assert view._subheading.text() == "1 work item"

    view._search.clear()
    view.refresh()

    assert view._table.rowCount() == 100
    assert not view._load_more.isHidden()
    assert view._subheading.text() == "Showing 100 of 150 work items"
