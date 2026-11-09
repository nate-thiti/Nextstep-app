"""Repository and Unit of Work ports.

The application layer depends on these protocols, not on SQLAlchemy. The
infrastructure layer supplies the concrete implementation.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from nextstep.domain.entities import AuditLogEntry, Checkpoint, WorkItem, WorkReference
from nextstep.domain.enums import WorkItemStatus


class WorkItemRepository(Protocol):
    def add(self, work_item: WorkItem) -> None: ...

    def get(self, work_item_id: UUID) -> WorkItem | None: ...

    def get_many(self, work_item_ids: list[UUID]) -> dict[UUID, WorkItem]: ...

    def list_items(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]: ...

    def count_items(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        work_item_ids: list[UUID] | None = None,
    ) -> int: ...

    def list_all(self) -> list[WorkItem]: ...

    def count(self) -> int: ...

    def delete(self, work_item: WorkItem) -> None: ...

    def list_groups(self) -> list[str]: ...

    def rename_group(self, old_name: str, new_name: str) -> int: ...

    def clear_group(self, name: str) -> int: ...


class CheckpointRepository(Protocol):
    def add(self, checkpoint: Checkpoint) -> None: ...

    def get(self, checkpoint_id: UUID) -> Checkpoint | None: ...

    def latest_for(self, work_item_id: UUID) -> Checkpoint | None: ...

    def latest_for_many(self, work_item_ids: list[UUID]) -> dict[UUID, Checkpoint]: ...

    def list_for(
        self, work_item_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Checkpoint]: ...

    def search(
        self,
        query: str,
        *,
        work_item_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Checkpoint]: ...

    def count_search(
        self,
        query: str,
        *,
        work_item_ids: list[UUID] | None = None,
    ) -> int: ...

    def list_all(self) -> list[Checkpoint]: ...

    def count(self) -> int: ...

    def delete(self, checkpoint: Checkpoint) -> None: ...


class ReferenceRepository(Protocol):
    def add(self, reference: WorkReference) -> None: ...

    def get(self, reference_id: UUID) -> WorkReference | None: ...

    def list_for_work_item(self, work_item_id: UUID) -> list[WorkReference]: ...

    def list_for_checkpoint(self, checkpoint_id: UUID) -> list[WorkReference]: ...

    def list_for_resume(
        self, work_item_id: UUID, checkpoint_id: UUID | None
    ) -> list[WorkReference]: ...

    def list_all(self) -> list[WorkReference]: ...

    def count(self) -> int: ...

    def delete(self, reference: WorkReference) -> None: ...


class SettingsRepository(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any) -> None: ...


class AuditLogRepository(Protocol):
    def add(self, entry: AuditLogEntry) -> None: ...

    def list_recent(self, limit: int = 50) -> list[AuditLogEntry]: ...

    def count(self) -> int: ...


class ArchivePort(Protocol):
    """Creates and inspects the zip archives used by backup and restore."""

    def snapshot(self, destination: Path) -> None: ...

    def write_archive(self, archive: Path, snapshot: Path, manifest: dict[str, Any]) -> None: ...

    def read_manifest(self, archive: Path) -> dict[str, Any]: ...

    def extract_database(self, archive: Path, destination: Path) -> None: ...

    def verify_database(self, database_path: Path) -> None: ...

    def database_revision(self, database_path: Path) -> str | None: ...

    def list_reference_ids(self, database_path: Path) -> list[str]: ...


class UnitOfWork(Protocol):
    work_items: WorkItemRepository
    checkpoints: CheckpointRepository
    references: ReferenceRepository
    settings: SettingsRepository
    audit_logs: AuditLogRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
