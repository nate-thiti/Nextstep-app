"""Deterministic Markdown handoff formatting."""

from __future__ import annotations

from nextstep.application.resume import ResumeData


def format_handoff_markdown(data: ResumeData, *, short: bool = False) -> str:
    """Build a portable handoff from the current Work Detail projection."""
    work_item = data.work_item
    checkpoint = data.latest_checkpoint
    lines = [f"# {work_item.title}", "", f"**Status:** {work_item.status.value}"]

    if work_item.group_name and not short:
        lines.append(f"**Group:** {work_item.group_name}")

    if work_item.goal:
        _append_section(lines, "Goal", work_item.goal)

    if checkpoint is None:
        _append_section(lines, "Latest progress", "No progress update yet.")
    else:
        if checkpoint.completed_work and not short:
            _append_section(lines, "Completed", checkpoint.completed_work)
        _append_section(lines, "Stopped at", checkpoint.stopped_at)
        if checkpoint.blockers:
            _append_section(lines, "Blockers", checkpoint.blockers)
        _append_section(lines, "Next actions", checkpoint.next_actions)
        if checkpoint.context_summary and not short:
            _append_section(lines, "Context", checkpoint.context_summary)

    if data.references and not short:
        lines.extend(["", "## References", ""])
        lines.extend(
            f"- {reference.label} ({reference.type.value}): {reference.target}"
            for reference in data.references
        )

    return "\n".join(lines).strip() + "\n"


def _append_section(lines: list[str], title: str, value: str) -> None:
    lines.extend(["", f"## {title}", "", value])
