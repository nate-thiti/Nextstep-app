"""SQLAlchemy-backed Unit of Work.

A unit of work owns one session. Services commit explicitly so multi-table use
cases (save checkpoint + update status) stay atomic.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from nextstep.application.ports import (
    AuditLogRepository,
    CheckpointRepository,
    ReferenceRepository,
    SettingsRepository,
    WorkItemRepository,
)
from nextstep.infrastructure.repositories import (
    SqlAlchemyAuditLogRepository,
    SqlAlchemyCheckpointRepository,
    SqlAlchemyReferenceRepository,
    SqlAlchemySettingsRepository,
    SqlAlchemyWorkItemRepository,
)


class SqlAlchemyUnitOfWork:
    work_items: WorkItemRepository
    checkpoints: CheckpointRepository
    references: ReferenceRepository
    settings: SettingsRepository
    audit_logs: AuditLogRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.work_items = SqlAlchemyWorkItemRepository(session)
        self.checkpoints = SqlAlchemyCheckpointRepository(session)
        self.references = SqlAlchemyReferenceRepository(session)
        self.settings = SqlAlchemySettingsRepository(session)
        self.audit_logs = SqlAlchemyAuditLogRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc_type is not None:
                self._session.rollback()
            self._session.close()
            self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()

    def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.rollback()
