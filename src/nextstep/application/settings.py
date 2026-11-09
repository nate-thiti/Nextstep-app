"""Local application settings stored in ``app_settings``."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from nextstep.application.ports import UnitOfWork
from nextstep.domain.errors import ValidationError

THEME_KEY = "ui.theme"
THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
WORK_LIST_VIEW_KEY = "ui.work_list_view"
WORK_LIST_VIEWS = ("focus", "compact")
DEFAULT_WORK_LIST_VIEW = "focus"
PINNED_WORK_ITEMS_KEY = "ui.pinned_work_items"
FOLLOW_UP_AT_KEY = "ui.follow_up_at"


class SettingsService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def get(self, key: str, default: Any = None) -> Any:
        with self._uow_factory() as uow:
            value = uow.settings.get(key)
        return default if value is None else value

    def set(self, key: str, value: Any) -> None:
        with self._uow_factory() as uow:
            uow.settings.set(key, value)
            uow.commit()

    def get_theme(self) -> str:
        theme = self.get(THEME_KEY, DEFAULT_THEME)
        return theme if theme in THEMES else DEFAULT_THEME

    def set_theme(self, theme: str) -> None:
        if theme not in THEMES:
            raise ValidationError("theme", "must be system, light or dark")
        self.set(THEME_KEY, theme)

    def get_work_list_view(self) -> str:
        view = self.get(WORK_LIST_VIEW_KEY, DEFAULT_WORK_LIST_VIEW)
        return view if view in WORK_LIST_VIEWS else DEFAULT_WORK_LIST_VIEW

    def set_work_list_view(self, view: str) -> None:
        if view not in WORK_LIST_VIEWS:
            raise ValidationError("work_list_view", "must be focus or compact")
        self.set(WORK_LIST_VIEW_KEY, view)

    def get_pinned_work_item_ids(self) -> set[UUID]:
        values = self.get(PINNED_WORK_ITEMS_KEY, [])
        if not isinstance(values, list):
            return set()
        result: set[UUID] = set()
        for value in values:
            try:
                result.add(UUID(str(value)))
            except ValueError:
                continue
        return result

    def set_work_item_pinned(self, work_item_id: UUID, pinned: bool) -> None:
        ids = self.get_pinned_work_item_ids()
        if pinned:
            ids.add(work_item_id)
        else:
            ids.discard(work_item_id)
        self.set(PINNED_WORK_ITEMS_KEY, sorted(str(value) for value in ids))

    def is_work_item_pinned(self, work_item_id: UUID) -> bool:
        return work_item_id in self.get_pinned_work_item_ids()

    def get_follow_up_at(self, work_item_id: UUID) -> datetime | None:
        values = self.get(FOLLOW_UP_AT_KEY, {})
        if not isinstance(values, dict):
            return None
        raw = values.get(str(work_item_id))
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_follow_up_at(self, work_item_id: UUID, value: datetime | None) -> None:
        values = self.get(FOLLOW_UP_AT_KEY, {})
        if not isinstance(values, dict):
            values = {}
        values = dict(values)
        if value is None:
            values.pop(str(work_item_id), None)
        else:
            values[str(work_item_id)] = value.isoformat()
        self.set(FOLLOW_UP_AT_KEY, values)

    def due_work_item_ids(self, now: datetime) -> set[UUID]:
        values = self.get(FOLLOW_UP_AT_KEY, {})
        if not isinstance(values, dict):
            return set()
        due: set[UUID] = set()
        for raw_id, raw_value in values.items():
            try:
                value = datetime.fromisoformat(str(raw_value))
                if value <= now:
                    due.add(UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue
        return due
