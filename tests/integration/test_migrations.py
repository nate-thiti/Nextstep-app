from __future__ import annotations

import sqlite3
from pathlib import Path

from nextstep.infrastructure.migrations import (
    alembic_config,
    backup_database,
    current_revision,
    head_revision,
    upgrade_to_head,
)


def test_upgrade_creates_database_without_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "nextstep.db"
    backups_dir = tmp_path / "backups"

    backup_path = upgrade_to_head(database_path, backups_dir)

    assert database_path.exists()
    assert backup_path is None
    assert not backups_dir.exists() or not list(backups_dir.iterdir())
    assert current_revision(database_path) is not None


def test_upgrade_backs_up_existing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "nextstep.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('keep me')")
        connection.commit()
    finally:
        connection.close()

    backup_path = upgrade_to_head(database_path, tmp_path / "backups")

    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.name.startswith("pre-migration-")

    backup = sqlite3.connect(backup_path)
    try:
        row = backup.execute("SELECT value FROM marker").fetchone()
    finally:
        backup.close()
    assert row == ("keep me",)


def test_upgrade_is_idempotent_at_head(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "nextstep.db"
    backups_dir = tmp_path / "backups"

    upgrade_to_head(database_path, backups_dir)
    backup_path = upgrade_to_head(database_path, backups_dir)

    assert backup_path is None
    assert not backups_dir.exists() or not list(backups_dir.iterdir())


def test_backup_database_copies_content(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE t (value INTEGER)")
        connection.execute("INSERT INTO t VALUES (42)")
        connection.commit()
    finally:
        connection.close()

    destination = backup_database(source, tmp_path / "nested" / "copy.db")

    assert destination.exists()
    copy = sqlite3.connect(destination)
    try:
        assert copy.execute("SELECT value FROM t").fetchone() == (42,)
    finally:
        copy.close()


def test_head_revision_is_configured(tmp_path: Path) -> None:
    config = alembic_config(tmp_path / "nextstep.db")

    assert head_revision(config) == "0002_audit_logs"
