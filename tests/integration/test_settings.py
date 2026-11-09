from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from nextstep.application.settings import (
    DEFAULT_THEME,
    DEFAULT_WORK_LIST_VIEW,
    SettingsService,
)
from nextstep.domain.errors import ValidationError


def test_default_theme_is_system(database) -> None:
    service = SettingsService(database.uow)

    assert service.get_theme() == DEFAULT_THEME


def test_theme_persists(database) -> None:
    SettingsService(database.uow).set_theme("dark")

    assert SettingsService(database.uow).get_theme() == "dark"


def test_invalid_theme_is_rejected(database) -> None:
    service = SettingsService(database.uow)

    with pytest.raises(ValidationError):
        service.set_theme("neon")


def test_unknown_value_falls_back_to_default(database) -> None:
    SettingsService(database.uow).set("ui.theme", "neon")

    assert SettingsService(database.uow).get_theme() == DEFAULT_THEME


def test_generic_settings_round_trip(database) -> None:
    service = SettingsService(database.uow)

    service.set("test.value", {"a": 1})

    assert service.get("test.value") == {"a": 1}
    assert service.get("missing", "fallback") == "fallback"


def test_work_list_view_defaults_and_persists(database) -> None:
    service = SettingsService(database.uow)

    assert service.get_work_list_view() == DEFAULT_WORK_LIST_VIEW
    service.set_work_list_view("compact")

    assert SettingsService(database.uow).get_work_list_view() == "compact"


def test_invalid_work_list_view_is_rejected(database) -> None:
    service = SettingsService(database.uow)

    with pytest.raises(ValidationError):
        service.set_work_list_view("cards")


def test_pin_and_follow_up_settings_persist(database) -> None:
    service = SettingsService(database.uow)
    work_id = uuid4()
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)

    service.set_work_item_pinned(work_id, True)
    service.set_follow_up_at(work_id, now - timedelta(minutes=1))

    reloaded = SettingsService(database.uow)
    assert reloaded.is_work_item_pinned(work_id)
    assert reloaded.get_follow_up_at(work_id) == now - timedelta(minutes=1)
    assert reloaded.due_work_item_ids(now) == {work_id}

    reloaded.set_work_item_pinned(work_id, False)
    reloaded.set_follow_up_at(work_id, None)
    assert not service.is_work_item_pinned(work_id)
    assert service.get_follow_up_at(work_id) is None
