"""Alembic environment for NextStep.

The database URL is resolved in this order:

1. ``sqlalchemy.url`` set programmatically (tests, tooling)
2. ``NEXTSTEP_DATABASE_URL`` environment variable
3. ``%LOCALAPPDATA%\\NextStep\\data\\nextstep.db`` (or ``NEXTSTEP_DATA_DIR``)
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

from nextstep.infrastructure.db import create_engine_for_url, sqlite_url
from nextstep.infrastructure.paths import DataPaths
from nextstep.infrastructure.tables import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    from_env = os.environ.get("NEXTSTEP_DATABASE_URL")
    if from_env:
        return from_env
    return sqlite_url(DataPaths.resolve().ensure().database_path)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine_for_url(_database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
