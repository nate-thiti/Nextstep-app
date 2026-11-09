"""Database engine, connection pragmas and custom column types."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, DateTime, Engine, String, create_engine, event
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator

if TYPE_CHECKING:
    from nextstep.infrastructure.uow import SqlAlchemyUnitOfWork

SQLITE_BUSY_TIMEOUT_MS = 5_000


class GUID(TypeDecorator[uuid.UUID]):
    """Store UUIDs as 36-character strings (MVP_SPEC section 9)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            raise TypeError(f"expected uuid.UUID, got {type(value)!r}")
        return str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(value)


class UtcDateTime(TypeDecorator[datetime]):
    """Persist timezone-aware UTC datetimes without losing the timezone.

    SQLite has no native timezone support, so values are stored as naive UTC
    and always returned as timezone-aware UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use timezone-aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class EnumType(TypeDecorator[Any]):
    """Store an enum as its text value and return the enum member."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type, length: int = 32) -> None:
        self._enum_class = enum_class
        super().__init__(length=length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return self._enum_class(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return self._enum_class(value)


def create_engine_for_url(url: str) -> Engine:
    """Create an engine with the pragmas required by MVP_SPEC section 9.5."""
    engine = create_engine(url, future=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _apply_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

    return engine


def sqlite_url(database_path: Path) -> str:
    """Build a SQLite URL that works with Windows absolute paths."""
    return f"sqlite+pysqlite:///{database_path.as_posix()}"


class Database:
    """Owns the engine and hands out units of work."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @classmethod
    def from_url(cls, url: str) -> Database:
        return cls(create_engine_for_url(url))

    @classmethod
    def open(cls, database_path: Path) -> Database:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        return cls.from_url(sqlite_url(database_path))

    def session(self) -> Session:
        return self._session_factory()

    def uow(self) -> SqlAlchemyUnitOfWork:
        from nextstep.infrastructure.uow import SqlAlchemyUnitOfWork

        return SqlAlchemyUnitOfWork(self._session_factory)

    def dispose(self) -> None:
        self.engine.dispose()
