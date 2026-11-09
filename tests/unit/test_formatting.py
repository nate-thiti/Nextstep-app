from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nextstep.desktop.widgets import format_local, format_relative


def test_format_local_handles_none() -> None:
    assert format_local(None) == "—"


def test_format_relative_minutes() -> None:
    assert format_relative(datetime.now(UTC) - timedelta(minutes=5)) == "5m ago"


def test_format_relative_hours_and_days() -> None:
    now = datetime.now(UTC)
    assert format_relative(now - timedelta(hours=3)) == "3h ago"
    assert format_relative(now - timedelta(days=2)) == "2d ago"


def test_format_relative_falls_back_to_absolute_for_old_values() -> None:
    old = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)

    rendered = format_relative(old)

    assert "ago" not in rendered
    assert "2025" in rendered
