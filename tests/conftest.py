"""Shared test fixtures: a migrated temporary database and fake clock."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command

from nextstep.application.checkpoints import CheckpointService
from nextstep.application.references import ReferenceService
from nextstep.application.work_items import WorkItemService
from nextstep.desktop.context import AppContext, build_context
from nextstep.infrastructure.db import Database
from nextstep.infrastructure.migrations import alembic_config
from nextstep.infrastructure.paths import DataPaths

# UI tests must run without a visible desktop.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeClock:
    """Controllable time source so ordering rules are deterministic."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> datetime:
        self._now += timedelta(**delta)
        return self._now


def upgrade_to_head(database_path: Path) -> None:
    command.upgrade(alembic_config(database_path), "head")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_path = tmp_path / "nextstep.db"
    upgrade_to_head(database_path)
    db = Database.open(database_path)
    yield db
    db.dispose()


@pytest.fixture
def work_items(database: Database, clock: FakeClock) -> WorkItemService:
    return WorkItemService(database.uow, clock)


@pytest.fixture
def checkpoints(database: Database, clock: FakeClock) -> CheckpointService:
    return CheckpointService(database.uow, clock)


@pytest.fixture
def references(database: Database, clock: FakeClock) -> ReferenceService:
    return ReferenceService(database.uow, clock)


@pytest.fixture
def app_context(tmp_path: Path, clock: FakeClock) -> Iterator[AppContext]:
    context = build_context(DataPaths.resolve(tmp_path / "appdata"), clock=clock)
    yield context
    context.close()
