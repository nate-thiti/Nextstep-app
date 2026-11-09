from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.domain.entities import WorkItem
from nextstep.domain.enums import ReferenceType, WorkItemStatus


def _bulk_create(database, count: int) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with database.uow() as uow:
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


def test_summaries_include_latest_checkpoint(work_items, checkpoints, clock) -> None:
    first = work_items.create(CreateWorkItem(title="First", group_name="Work"))
    second = work_items.create(CreateWorkItem(title="Second"))
    clock.advance(minutes=1)
    checkpoints.save(
        SaveCheckpoint(
            work_item_id=first.id,
            stopped_at="blocked",
            next_actions="ask reviewer",
            blockers="waiting",
        )
    )
    clock.advance(minutes=1)
    latest = checkpoints.save(
        SaveCheckpoint(
            work_item_id=first.id,
            stopped_at="unblocked",
            next_actions="write tests",
        )
    )

    summaries = {summary.work_item.id: summary for summary in work_items.list_summaries()}

    assert summaries[first.id].latest_checkpoint is not None
    assert summaries[first.id].latest_checkpoint.id == latest.id
    assert summaries[first.id].has_blocker is False
    assert summaries[second.id].latest_checkpoint is None
    assert summaries[second.id].has_blocker is False


def test_summary_reports_blocker(work_items, checkpoints) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="stuck",
            next_actions="retry",
            blockers="token expired",
        )
    )

    summary = work_items.list_summaries()[0]

    assert summary.has_blocker is True


def test_search_matches_title_goal_group_and_checkpoint_text(work_items, checkpoints) -> None:
    login = work_items.create(CreateWorkItem(title="Fix login", group_name="Auth"))
    docs = work_items.create(CreateWorkItem(title="Write docs", goal="API reference"))
    other = work_items.create(CreateWorkItem(title="Unrelated"))
    checkpoints.save(
        SaveCheckpoint(
            work_item_id=other.id,
            stopped_at="refresh token fails",
            next_actions="check cookie",
        )
    )

    assert [item.id for item in work_items.list_items(search="login")] == [login.id]
    assert [item.id for item in work_items.list_items(search="reference")] == [docs.id]
    assert [item.id for item in work_items.list_items(search="auth")] == [login.id]
    assert [item.id for item in work_items.list_items(search="cookie")] == [other.id]
    assert work_items.list_items(search="nothing matches this") == []


def test_search_matches_reference_label_and_target(work_items, references) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.URL,
            label="Design doc",
            target="https://example.com/specification",
        )
    )

    assert [found.id for found in work_items.list_items(search="design")] == [item.id]
    assert [found.id for found in work_items.list_items(search="specification")] == [item.id]


def test_search_treats_like_wildcards_literally(work_items) -> None:
    percent = work_items.create(CreateWorkItem(title="100% complete"))
    work_items.create(CreateWorkItem(title="100 percent"))

    assert [item.id for item in work_items.list_items(search="%")] == [percent.id]
    assert work_items.list_items(search="_") == []


def test_search_combines_with_status_filter(work_items) -> None:
    active = work_items.create(CreateWorkItem(title="Active login"))
    paused = work_items.create(CreateWorkItem(title="Paused login", status=WorkItemStatus.PAUSED))

    assert [item.id for item in work_items.list_items(search="login")] == [
        active.id,
        paused.id,
    ]
    assert [
        item.id for item in work_items.list_items(search="login", status=WorkItemStatus.PAUSED)
    ] == [paused.id]


def test_page_summaries_reaches_items_beyond_the_first_page(work_items, database) -> None:
    _bulk_create(database, 650)

    first = work_items.page_summaries(limit=100, offset=0)
    assert first.total == 650
    assert len(first.summaries) == 100
    assert first.has_more

    last = work_items.page_summaries(limit=100, offset=600)
    assert last.total == 650
    assert len(last.summaries) == 50
    assert not last.has_more
    assert "Task 649" in {summary.work_item.title for summary in last.summaries}


def test_page_summaries_search_and_filter_use_the_whole_dataset(work_items, database) -> None:
    _bulk_create(database, 650)
    later = work_items.create(CreateWorkItem(title="Only in later", group_name="Later"))

    search = work_items.page_summaries(search="Task 649", limit=100)
    assert search.total == 1
    assert [summary.work_item.title for summary in search.summaries] == ["Task 649"]

    grouped = work_items.page_summaries(group_name="Later", limit=100)
    assert grouped.total == 1
    assert [summary.work_item.id for summary in grouped.summaries] == [later.id]
