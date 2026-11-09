"""Schema upgrades at application startup.

A SQLite-consistent copy is written to ``backups/`` before any upgrade that
changes an existing database, so a failed migration never destroys user data.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from nextstep.infrastructure.db import sqlite_url


def migrations_dir() -> Path:
    """Migration resources inside the installed package.

    Using package resources keeps migrations available when NextStep is
    installed from a wheel instead of run from a source checkout.
    """
    return Path(str(resources.files("nextstep.migrations")))


def alembic_config(database_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


def current_revision(database_path: Path) -> str | None:
    if not database_path.exists():
        return None
    engine = create_engine(sqlite_url(database_path))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head_revision(config: Config) -> str | None:
    return ScriptDirectory.from_config(config).get_current_head()


def schema_revisions(database_path: Path) -> set[str]:
    """Every schema revision this build knows how to open."""
    config = alembic_config(database_path)
    return {revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()}


def supports_revision(database_path: Path, revision: str) -> bool:
    return revision in schema_revisions(database_path)


def backup_database(database_path: Path, destination: Path) -> Path:
    """Copy a live SQLite database using the online backup API."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(database_path)
    try:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return destination


def upgrade_to_head(database_path: Path, backups_dir: Path) -> Path | None:
    """Upgrade the schema and return the safety backup path, if one was made."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = alembic_config(database_path)

    backup_path: Path | None = None
    existing_revision = current_revision(database_path)
    has_data = database_path.exists() and database_path.stat().st_size > 0
    if has_data and existing_revision != head_revision(config):
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup_path = backup_database(database_path, backups_dir / f"pre-migration-{timestamp}.db")

    command.upgrade(config, "head")
    return backup_path
