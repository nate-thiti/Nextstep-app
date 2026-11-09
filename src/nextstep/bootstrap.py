"""Shared composition root for the desktop app and the local MCP server.

Nothing in this module imports PySide6. The desktop package re-exports these
names so existing UI code keeps one import path while the MCP server can build
the same Core Services without depending on the UI layer.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from nextstep import __version__
from nextstep.application.audit import AuditService
from nextstep.application.checkpoints import CheckpointService
from nextstep.application.clock import utcnow
from nextstep.application.mcp_commands import McpCommandService
from nextstep.application.mcp_policy import McpPolicyService
from nextstep.application.mcp_queries import McpQueryService
from nextstep.application.portability import (
    PortabilityService,
)
from nextstep.application.references import ReferenceService
from nextstep.application.resume import ResumeService
from nextstep.application.settings import SettingsService
from nextstep.application.work_items import WorkItemService
from nextstep.infrastructure.archive import ZipArchive
from nextstep.infrastructure.db import Database
from nextstep.infrastructure.migrations import (
    alembic_config,
    head_revision,
    supports_revision,
    upgrade_to_head,
)
from nextstep.infrastructure.paths import DataPaths

RESTORE_MARKER_NAME = "restored-references.flag"
RESTORE_MARKER_VERSION = 1


@dataclass
class AppContext:
    database: Database
    paths: DataPaths
    work_items: WorkItemService
    checkpoints: CheckpointService
    references: ReferenceService
    resume: ResumeService
    settings: SettingsService
    portability: PortabilityService
    audit: AuditService
    mcp_policy: McpPolicyService
    mcp_queries: McpQueryService
    mcp_commands: McpCommandService

    def close(self) -> None:
        self.database.dispose()

    def restore_confirmation_pending(self) -> bool:
        """Whether any restored reference still needs explicit confirmation."""
        present, _ = self._restore_marker_state()
        return present

    def reference_requires_confirmation(self, reference_id: UUID) -> bool:
        present, pending = self._restore_marker_state()
        if not present:
            return False
        # An unreadable marker must not grant trust to every restored reference.
        return not pending or str(reference_id) in pending

    def clear_reference_confirmation(self, reference_id: UUID) -> None:
        """Forget one confirmed reference, keeping the rest pending."""
        present, pending = self._restore_marker_state()
        if not present or str(reference_id) not in pending:
            return
        remaining = [value for value in pending if value != str(reference_id)]
        self._write_restore_marker(remaining)

    def _restore_marker(self) -> Path:
        return self.paths.config_dir / RESTORE_MARKER_NAME

    def _restore_marker_state(self) -> tuple[bool, list[str]]:
        marker = self._restore_marker()
        if not marker.exists():
            return False, []
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return True, []
        if not isinstance(payload, dict):
            return True, []
        if payload.get("format_version") != RESTORE_MARKER_VERSION:
            return True, []
        ids = payload.get("reference_ids")
        if not isinstance(ids, list):
            return True, []
        return True, [value for value in ids if isinstance(value, str)]

    def _write_restore_marker(self, reference_ids: list[str]) -> None:
        marker = self._restore_marker()
        if not reference_ids:
            marker.unlink(missing_ok=True)
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "format_version": RESTORE_MARKER_VERSION,
                    "reference_ids": reference_ids,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def build_context(
    paths: DataPaths | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> AppContext:
    resolved = (paths or DataPaths.resolve()).ensure()
    upgrade_to_head(resolved.database_path, resolved.backups_dir)

    database = Database.open(resolved.database_path)
    uow_factory = database.uow
    schema_config = alembic_config(resolved.database_path)

    work_items = WorkItemService(uow_factory, clock)
    checkpoints = CheckpointService(uow_factory, clock)
    references = ReferenceService(uow_factory, clock)
    resume = ResumeService(uow_factory)
    settings = SettingsService(uow_factory)
    audit = AuditService(uow_factory, clock)
    mcp_policy = McpPolicyService(settings)

    return AppContext(
        database=database,
        paths=resolved,
        work_items=work_items,
        checkpoints=checkpoints,
        references=references,
        resume=resume,
        settings=settings,
        portability=PortabilityService(
            uow_factory=uow_factory,
            archiver=ZipArchive(resolved.database_path),
            database_path=resolved.database_path,
            backups_dir=resolved.backups_dir,
            app_version=__version__,
            schema_version=lambda: head_revision(schema_config),
            supports_schema=lambda version: supports_revision(resolved.database_path, version),
            clock=clock,
            close_database=database.dispose,
            restore_marker=resolved.config_dir / RESTORE_MARKER_NAME,
        ),
        mcp_policy=mcp_policy,
        mcp_queries=McpQueryService(
            work_items=work_items,
            checkpoints=checkpoints,
            resume=resume,
            policy=mcp_policy,
        ),
        audit=audit,
        mcp_commands=McpCommandService(
            work_items=work_items,
            checkpoints=checkpoints,
            references=references,
            policy=mcp_policy,
            audit=audit,
        ),
    )
