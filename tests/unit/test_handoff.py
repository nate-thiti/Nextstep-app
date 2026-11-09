from datetime import UTC, datetime
from uuid import uuid4

from nextstep.application.handoff import format_handoff_markdown
from nextstep.application.resume import ResumeData
from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.domain.enums import ReferenceType, WorkItemStatus


def test_format_handoff_includes_latest_context_and_references() -> None:
    now = datetime(2026, 11, 7, tzinfo=UTC)
    work_item = WorkItem(
        id=uuid4(),
        title="Fix login refresh",
        status=WorkItemStatus.ACTIVE,
        goal="Keep the session alive after refresh",
        group_name="Authentication",
        created_at=now,
        updated_at=now,
    )
    checkpoint = Checkpoint(
        id=uuid4(),
        work_item_id=work_item.id,
        stopped_at="Integration test still fails",
        next_actions="Inspect Set-Cookie after refresh",
        completed_work="Fixed the middleware",
        blockers="Token expiry behavior is unclear",
        context_summary="The failure only happens after a hard refresh.",
        status_after_save=WorkItemStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    reference = WorkReference(
        id=uuid4(),
        work_item_id=work_item.id,
        type=ReferenceType.GIT_REPOSITORY,
        label="Auth repository",
        target=r"D:\projects\auth",
        created_at=now,
        updated_at=now,
    )

    result = format_handoff_markdown(ResumeData(work_item, checkpoint, [checkpoint], [reference]))

    assert result == (
        "# Fix login refresh\n"
        "\n"
        "**Status:** active\n"
        "**Group:** Authentication\n"
        "\n"
        "## Goal\n"
        "\n"
        "Keep the session alive after refresh\n"
        "\n"
        "## Completed\n"
        "\n"
        "Fixed the middleware\n"
        "\n"
        "## Stopped at\n"
        "\n"
        "Integration test still fails\n"
        "\n"
        "## Blockers\n"
        "\n"
        "Token expiry behavior is unclear\n"
        "\n"
        "## Next actions\n"
        "\n"
        "Inspect Set-Cookie after refresh\n"
        "\n"
        "## Context\n"
        "\n"
        "The failure only happens after a hard refresh.\n"
        "\n"
        "## References\n"
        "\n"
        "- Auth repository (git_repository): D:\\projects\\auth\n"
    )


def test_format_handoff_without_checkpoint_still_has_useful_content() -> None:
    now = datetime(2026, 11, 7, tzinfo=UTC)
    work_item = WorkItem(
        id=uuid4(),
        title="Plan release",
        status=WorkItemStatus.PAUSED,
        created_at=now,
        updated_at=now,
    )

    result = format_handoff_markdown(ResumeData(work_item, None, [], []))

    assert result == (
        "# Plan release\n\n**Status:** paused\n\n## Latest progress\n\nNo progress update yet.\n"
    )


def test_short_handoff_omits_history_context_and_references() -> None:
    now = datetime(2026, 11, 7, tzinfo=UTC)
    work_item = WorkItem(
        id=uuid4(),
        title="Task",
        status=WorkItemStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    checkpoint = Checkpoint(
        id=uuid4(),
        work_item_id=work_item.id,
        stopped_at="Here",
        next_actions="Continue",
        completed_work="Done",
        context_summary="Internal context",
        status_after_save=WorkItemStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    result = format_handoff_markdown(
        ResumeData(work_item, checkpoint, [checkpoint], []), short=True
    )

    assert "## Stopped at\n\nHere" in result
    assert "## Next actions\n\nContinue" in result
    assert "Done" not in result
    assert "Internal context" not in result
