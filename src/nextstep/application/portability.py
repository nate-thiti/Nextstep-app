"""Backup, restore and JSON export (MVP_SPEC section 10)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nextstep.application.clock import utcnow
from nextstep.application.ports import ArchivePort, UnitOfWork
from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.domain.errors import ArchiveError, RestoreRequiresRestartError

EXPORT_VERSION = 1
BACKUP_FORMAT_VERSION = 1

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupResult:
    path: Path
    created_at: datetime
    work_item_count: int
    checkpoint_count: int
    reference_count: int


@dataclass(frozen=True)
class RestoreResult:
    path: Path
    safety_backup: Path


@dataclass(frozen=True)
class ExportResult:
    path: Path
    exported_at: datetime
    work_item_count: int
    checkpoint_count: int
    reference_count: int


def _with_suffix(path: Path, suffix: str) -> Path:
    resolved = path.expanduser()
    if resolved.suffix.lower() == suffix:
        return resolved
    return resolved.with_name(resolved.name + suffix)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _work_item_payload(item: WorkItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "title": item.title,
        "goal": item.goal,
        "status": item.status.value,
        "group_name": item.group_name,
        "created_at": _isoformat(item.created_at),
        "updated_at": _isoformat(item.updated_at),
    }


def _checkpoint_payload(checkpoint: Checkpoint) -> dict[str, Any]:
    return {
        "id": str(checkpoint.id),
        "work_item_id": str(checkpoint.work_item_id),
        "completed_work": checkpoint.completed_work,
        "stopped_at": checkpoint.stopped_at,
        "blockers": checkpoint.blockers,
        "next_actions": checkpoint.next_actions,
        "context_summary": checkpoint.context_summary,
        "status_after_save": checkpoint.status_after_save.value,
        "created_at": _isoformat(checkpoint.created_at),
        "updated_at": _isoformat(checkpoint.updated_at),
    }


def _reference_payload(reference: WorkReference) -> dict[str, Any]:
    return {
        "id": str(reference.id),
        "work_item_id": str(reference.work_item_id),
        "checkpoint_id": (
            str(reference.checkpoint_id) if reference.checkpoint_id is not None else None
        ),
        "type": reference.type.value,
        "label": reference.label,
        "target": reference.target,
        "metadata": dict(reference.metadata),
        "created_at": _isoformat(reference.created_at),
        "updated_at": _isoformat(reference.updated_at),
    }


class PortabilityService:
    """Create user-facing backups, restore them and export portable JSON."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        archiver: ArchivePort,
        database_path: Path,
        backups_dir: Path,
        app_version: str,
        schema_version: Callable[[], str | None],
        supports_schema: Callable[[str], bool],
        clock: Callable[[], datetime] = utcnow,
        close_database: Callable[[], None] | None = None,
        restore_marker: Path | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._archiver = archiver
        self._database_path = database_path
        self._backups_dir = backups_dir
        self._app_version = app_version
        self._schema_version = schema_version
        self._supports_schema = supports_schema
        self._clock = clock
        self._close_database = close_database
        self._restore_marker = restore_marker

    def backup(self, destination: Path) -> BackupResult:
        target = _with_suffix(destination, ".zip")
        created_at = self._clock()
        counts = self._counts()
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": self._app_version,
            "schema_version": self._current_schema_version(),
            "created_at": _isoformat(created_at),
            "counts": {
                "work_items": counts[0],
                "checkpoints": counts[1],
                "references": counts[2],
            },
        }

        try:
            with tempfile.TemporaryDirectory(prefix="nextstep-snapshot-") as directory:
                snapshot = Path(directory) / "nextstep.db"
                self._archiver.snapshot(snapshot)
                self._archiver.write_archive(target, snapshot, manifest)
        except OSError as error:
            raise ArchiveError(f"Could not write the backup to {target}: {error}") from error

        return BackupResult(
            path=target,
            created_at=created_at,
            work_item_count=counts[0],
            checkpoint_count=counts[1],
            reference_count=counts[2],
        )

    def restore(self, archive: Path) -> RestoreResult:
        source = archive.expanduser()
        manifest = self._archiver.read_manifest(source)

        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ArchiveError("This backup was created by an unsupported version of NextStep.")

        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, str) or not self._supports_schema(schema_version):
            raise ArchiveError(
                "This backup uses a database schema that this version of NextStep cannot open."
            )

        timestamp = self._clock().strftime("%Y%m%d-%H%M%S-%f")
        safety_backup = self._backups_dir / f"pre-restore-{timestamp}.zip"

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=".nextstep-restore-", suffix=".db", dir=self._database_path.parent
        )
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            self._archiver.extract_database(source, temporary)
            self._archiver.verify_database(temporary)
            self._validate_restored_revision(temporary, schema_version)
            reference_ids = self._archiver.list_reference_ids(temporary)
            self.backup(safety_backup)
            previous_marker = self._read_restore_marker()
            self._write_restore_marker(reference_ids)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

        if self._close_database is not None:
            self._close_database()

        try:
            for suffix in ("-wal", "-shm"):
                Path(f"{self._database_path}{suffix}").unlink(missing_ok=True)
            os.replace(temporary, self._database_path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            self._restore_previous_marker(previous_marker)
            raise RestoreRequiresRestartError(
                "NextStep could not replace the current database. "
                f"The previous data is still on disk. Safety backup: {safety_backup}. "
                "Close NextStep, reopen it, and try the restore again. "
                f"Details: {error}"
            ) from error

        return RestoreResult(path=source, safety_backup=safety_backup)

    def _validate_restored_revision(self, database_path: Path, manifest_revision: str) -> None:
        actual = self._archiver.database_revision(database_path)
        if actual is None or actual != manifest_revision:
            raise ArchiveError("The backup manifest does not match the database schema revision.")
        if not self._supports_schema(actual):
            raise ArchiveError(
                "This backup uses a database schema that this version of NextStep cannot open."
            )

    def _write_restore_marker(self, reference_ids: list[str]) -> None:
        """Persist restored-reference trust state before replacing live data.

        A missing marker would make restored paths and URLs look trusted.  Marker
        creation is therefore part of the restore transaction: failure aborts
        before the live database is closed or replaced.
        """
        if self._restore_marker is None:
            return
        temporary: Path | None = None
        try:
            self._restore_marker.parent.mkdir(parents=True, exist_ok=True)
            if not reference_ids:
                self._restore_marker.unlink(missing_ok=True)
                return
            handle, temporary_name = tempfile.mkstemp(
                prefix=".nextstep-restore-marker-",
                suffix=".json",
                dir=self._restore_marker.parent,
            )
            os.close(handle)
            temporary = Path(temporary_name)
            temporary.write_text(
                json.dumps(
                    {"format_version": 1, "reference_ids": reference_ids},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, self._restore_marker)
        except OSError as error:
            raise ArchiveError(
                "Could not save restored-reference confirmation state; "
                "the current database was not changed."
            ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _read_restore_marker(self) -> bytes | None:
        if self._restore_marker is None or not self._restore_marker.exists():
            return None
        try:
            return self._restore_marker.read_bytes()
        except OSError as error:
            raise ArchiveError(
                "Could not preserve the existing restored-reference confirmation state; "
                "the current database was not changed."
            ) from error

    def _restore_previous_marker(self, content: bytes | None) -> None:
        """Best-effort rollback after database replacement fails."""
        if self._restore_marker is None:
            return
        temporary: Path | None = None
        try:
            if content is None:
                self._restore_marker.unlink(missing_ok=True)
                return
            self._restore_marker.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(
                prefix=".nextstep-restore-marker-rollback-",
                suffix=".json",
                dir=self._restore_marker.parent,
            )
            os.close(handle)
            temporary = Path(temporary_name)
            temporary.write_bytes(content)
            os.replace(temporary, self._restore_marker)
        except OSError:
            logger.exception("could not restore the previous reference confirmation marker")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def export_json(self, destination: Path) -> ExportResult:
        target = _with_suffix(destination, ".json")
        exported_at = self._clock()

        with self._uow_factory() as uow:
            work_items = uow.work_items.list_all()
            checkpoints = uow.checkpoints.list_all()
            references = uow.references.list_all()

        payload = {
            "export_version": EXPORT_VERSION,
            "exported_at": _isoformat(exported_at),
            "app_version": self._app_version,
            "work_items": [_work_item_payload(item) for item in work_items],
            "checkpoints": [_checkpoint_payload(checkpoint) for checkpoint in checkpoints],
            "references": [_reference_payload(reference) for reference in references],
        }
        self._write_json(target, payload)

        return ExportResult(
            path=target,
            exported_at=exported_at,
            work_item_count=len(work_items),
            checkpoint_count=len(checkpoints),
            reference_count=len(references),
        )

    def _counts(self) -> tuple[int, int, int]:
        with self._uow_factory() as uow:
            return (
                uow.work_items.count(),
                uow.checkpoints.count(),
                uow.references.count(),
            )

    def _current_schema_version(self) -> str:
        version = self._schema_version()
        if version is None:
            raise ArchiveError("The database schema version could not be determined.")
        return version

    @staticmethod
    def _write_json(destination: Path, payload: dict[str, Any]) -> None:
        temporary: Path | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(
                prefix=".nextstep-export-", suffix=".json", dir=destination.parent
            )
            os.close(handle)
            temporary = Path(temporary_name)
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, destination)
        except OSError as error:
            raise ArchiveError(f"Could not write the export to {destination}: {error}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
