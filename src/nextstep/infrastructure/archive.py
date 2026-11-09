"""Zip archives and SQLite snapshots (MVP_SPEC section 10).

A backup is a zip file with two members: a SQLite-consistent snapshot of the
database and a JSON manifest. Nothing that a Reference points to is copied.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from nextstep.domain.errors import ArchiveError

ARCHIVE_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "nextstep.db"

_REQUIRED_TABLES = {
    "alembic_version",
    "app_settings",
    "checkpoints",
    "work_items",
    "work_references",
}


class ZipArchive:
    """Create and inspect NextStep backup archives for one database file."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def snapshot(self, destination: Path) -> None:
        """Copy the live database with the SQLite online backup API."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source = sqlite3.connect(self._database_path)
            try:
                target = sqlite3.connect(destination)
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                source.close()
        except sqlite3.DatabaseError as error:
            raise ArchiveError("Could not read the current database for backup.") from error

    def write_archive(self, archive: Path, snapshot: Path, manifest: dict[str, Any]) -> None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=".nextstep-backup-", suffix=".zip", dir=archive.parent
        )
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(snapshot, DATABASE_NAME)
                bundle.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
            os.replace(temporary, archive)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def read_manifest(self, archive: Path) -> dict[str, Any]:
        if not archive.exists():
            raise ArchiveError(f"Backup file not found: {archive}")
        try:
            with zipfile.ZipFile(archive) as bundle:
                try:
                    raw = bundle.read(MANIFEST_NAME)
                except KeyError as error:
                    raise ArchiveError(
                        "This file is not a NextStep backup: manifest.json is missing."
                    ) from error
        except zipfile.BadZipFile as error:
            raise ArchiveError("This file is not a valid zip archive.") from error

        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArchiveError("The backup manifest is unreadable.") from error
        if not isinstance(manifest, dict):
            raise ArchiveError("The backup manifest is invalid.")
        return manifest

    def extract_database(self, archive: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive) as bundle:
                try:
                    member = bundle.getinfo(DATABASE_NAME)
                except KeyError as error:
                    raise ArchiveError(
                        "The backup does not contain a NextStep database."
                    ) from error
                with bundle.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
        except zipfile.BadZipFile as error:
            raise ArchiveError("This file is not a valid zip archive.") from error

    def verify_database(self, database_path: Path) -> None:
        try:
            connection = sqlite3.connect(database_path)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise ArchiveError("The backup database is damaged.")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise ArchiveError("The backup database is unreadable.") from error

        if _REQUIRED_TABLES - tables:
            raise ArchiveError("The backup database is missing expected tables.")

    def database_revision(self, database_path: Path) -> str | None:
        """Read the Alembic revision recorded inside the extracted database."""
        try:
            connection = sqlite3.connect(database_path)
            try:
                row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise ArchiveError("The backup database is unreadable.") from error
        return str(row[0]) if row else None

    def list_reference_ids(self, database_path: Path) -> list[str]:
        try:
            connection = sqlite3.connect(database_path)
            try:
                rows = connection.execute("SELECT id FROM work_references").fetchall()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise ArchiveError("The backup database is unreadable.") from error
        return [str(row[0]) for row in rows]
