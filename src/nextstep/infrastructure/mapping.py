"""Imperative mappings between domain dataclasses and database tables.

Imperative mapping keeps the domain free of SQLAlchemy while still giving the
repositories change tracking and identity mapping.
"""

from __future__ import annotations

from sqlalchemy.orm import registry

from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.infrastructure.tables import (
    checkpoints,
    metadata,
    work_items,
    work_references,
)

mapper_registry = registry(metadata=metadata)

mapper_registry.map_imperatively(WorkItem, work_items)

mapper_registry.map_imperatively(Checkpoint, checkpoints)

mapper_registry.map_imperatively(
    WorkReference,
    work_references,
    properties={"metadata": work_references.c.metadata_json},
)
