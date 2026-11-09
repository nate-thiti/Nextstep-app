"""Reference use cases (MVP_SPEC section 8)."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID, uuid4

from nextstep.application.clock import utcnow
from nextstep.application.dto import AddReference, UpdateReference
from nextstep.application.ports import UnitOfWork
from nextstep.domain.entities import WorkReference
from nextstep.domain.enums import ReferenceType
from nextstep.domain.errors import NotFoundError, ValidationError
from nextstep.domain.validation import (
    MAX_REFERENCE_LABEL_LENGTH,
    MAX_REFERENCE_TARGET_LENGTH,
    required_text,
)

_ALLOWED_URL_SCHEMES = ("http", "https")


def normalize_target(reference_type: ReferenceType, target: str) -> str:
    """Normalize a reference target and reject unsupported values."""
    if reference_type is ReferenceType.URL:
        parsed = urlparse(target)
        if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
            raise ValidationError("target", "must be an http or https URL")
        return target

    normalized = os.path.normpath(target)
    if not os.path.isabs(normalized):
        raise ValidationError("target", "must be an absolute path")
    return normalized


class ReferenceService:
    """Attach file, folder, URL and Git repository pointers to work."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def add(self, command: AddReference) -> WorkReference:
        label = required_text(command.label, "label", MAX_REFERENCE_LABEL_LENGTH)
        target = normalize_target(
            command.type,
            required_text(command.target, "target", MAX_REFERENCE_TARGET_LENGTH),
        )
        now = self._clock()

        with self._uow_factory() as uow:
            if uow.work_items.get(command.work_item_id) is None:
                raise NotFoundError("Work item", command.work_item_id)

            if command.checkpoint_id is not None:
                checkpoint = uow.checkpoints.get(command.checkpoint_id)
                if checkpoint is None:
                    raise NotFoundError("Checkpoint", command.checkpoint_id)
                if checkpoint.work_item_id != command.work_item_id:
                    raise ValidationError("checkpoint_id", "does not belong to the given work item")

            reference = WorkReference(
                id=uuid4(),
                work_item_id=command.work_item_id,
                checkpoint_id=command.checkpoint_id,
                type=command.type,
                label=label,
                target=target,
                metadata=dict(command.metadata or {}),
                created_at=now,
                updated_at=now,
            )
            uow.references.add(reference)
            uow.commit()

        return reference

    def get(self, reference_id: UUID) -> WorkReference:
        with self._uow_factory() as uow:
            return self._require(uow, reference_id)

    def list_for_work_item(self, work_item_id: UUID) -> list[WorkReference]:
        with self._uow_factory() as uow:
            return uow.references.list_for_work_item(work_item_id)

    def list_for_checkpoint(self, checkpoint_id: UUID) -> list[WorkReference]:
        with self._uow_factory() as uow:
            return uow.references.list_for_checkpoint(checkpoint_id)

    def update(self, reference_id: UUID, command: UpdateReference) -> WorkReference:
        changes = command.model_dump(exclude_unset=True)

        with self._uow_factory() as uow:
            reference = self._require(uow, reference_id)

            if "label" in changes:
                reference.label = required_text(
                    changes["label"], "label", MAX_REFERENCE_LABEL_LENGTH
                )
            if "target" in changes:
                reference.target = normalize_target(
                    reference.type,
                    required_text(changes["target"], "target", MAX_REFERENCE_TARGET_LENGTH),
                )
            if "metadata" in changes:
                reference.metadata = dict(changes["metadata"] or {})

            reference.updated_at = self._clock()
            uow.commit()

        return reference

    def delete(self, reference_id: UUID) -> None:
        with self._uow_factory() as uow:
            reference = self._require(uow, reference_id)
            uow.references.delete(reference)
            uow.commit()

    @staticmethod
    def _require(uow: UnitOfWork, reference_id: UUID) -> WorkReference:
        reference = uow.references.get(reference_id)
        if reference is None:
            raise NotFoundError("Reference", reference_id)
        return reference
