from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from nextstep.application.dto import CreateWorkItem, SaveCheckpoint
from nextstep.infrastructure.db import Database
from nextstep.infrastructure.migrations import alembic_config


def test_sqlite_pragmas_are_applied(database: Database) -> None:
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() >= 5000


def test_migration_creates_expected_tables(database: Database) -> None:
    tables = set(inspect(database.engine).get_table_names())

    assert {
        "work_items",
        "checkpoints",
        "work_references",
        "app_settings",
        "audit_logs",
        "alembic_version",
    } <= tables


def test_audit_log_stores_metadata_columns_only(database: Database) -> None:
    columns = {column["name"] for column in inspect(database.engine).get_columns("audit_logs")}

    assert columns == {
        "id",
        "created_at",
        "actor",
        "tool_name",
        "operation",
        "outcome",
        "work_item_id",
        "changed_fields_json",
        "error_code",
    }


def test_foreign_keys_are_enforced(database: Database) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO checkpoints (id, work_item_id, stopped_at, next_actions,"
            " status_after_save, created_at, updated_at)"
            " VALUES ('c1', 'missing', 'x', 'y', 'active',"
            " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )


def test_unicode_round_trip(work_items, checkpoints) -> None:
    item = work_items.create(
        CreateWorkItem(
            title="แก้ระบบล็อกอิน",
            goal="ตรวจสอบ refresh token",
            group_name="งานด่วน",
        )
    )
    checkpoint = checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="integration test ยังไม่ผ่าน",
            next_actions="ตรวจ cookie หลัง refresh",
            completed_work="แก้ middleware แล้ว",
            blockers="token หมดอายุ",
        )
    )

    assert work_items.get(item.id).title == "แก้ระบบล็อกอิน"
    stored = checkpoints.get(checkpoint.id)
    assert stored.next_actions == "ตรวจ cookie หลัง refresh"
    assert stored.blockers == "token หมดอายุ"


def test_timestamps_are_utc_aware(work_items, checkpoints) -> None:
    item = work_items.create(CreateWorkItem(title="Task"))
    checkpoint = checkpoints.save(
        SaveCheckpoint(work_item_id=item.id, stopped_at="here", next_actions="next")
    )

    assert checkpoint.created_at.tzinfo is UTC
    assert checkpoint.created_at.utcoffset() is not None
    assert item.created_at.tzinfo is UTC
    assert item.created_at <= datetime.now(UTC)


def test_downgrade_removes_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "downgrade.db"
    config = alembic_config(database_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    database = Database.open(database_path)
    try:
        assert set(inspect(database.engine).get_table_names()) == {"alembic_version"}
    finally:
        database.dispose()
