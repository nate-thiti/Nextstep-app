"""Write tools exposed to the local MCP server (Phase 6).

Every method checks the capability policy first, calls the same Core Service the
desktop uses, and records a privacy-safe audit entry. Permanent Work Item delete
is intentionally not exposed to MCP.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TypeVar
from uuid import UUID, uuid4

from nextstep.application.audit import AuditService
from nextstep.application.checkpoints import CheckpointService
from nextstep.application.dto import (
    AddReference,
    CreateWorkItem,
    SaveCheckpoint,
    UpdateReference,
    UpdateWorkItem,
)
from nextstep.application.mcp_policy import (
    McpOperation,
    McpPolicyService,
    McpScope,
    McpWritePolicy,
)
from nextstep.application.mcp_queries import (
    CheckpointOut,
    McpModel,
    ReferenceOut,
    WorkItemOut,
    _checkpoint_out,
    _reference_out,
    _work_item_out,
)
from nextstep.application.references import ReferenceService
from nextstep.application.work_items import WorkItemService
from nextstep.domain.enums import AuditOutcome, ReferenceType, WorkItemStatus
from nextstep.domain.errors import (
    AccessDeniedError,
    NextStepError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AuditWriteOut(McpModel):
    audit_id: UUID | None
    audit_recorded: bool


class WorkItemWriteOut(AuditWriteOut):
    work_item: WorkItemOut


class CheckpointWriteOut(AuditWriteOut):
    checkpoint: CheckpointOut


class ReferenceWriteOut(AuditWriteOut):
    reference: ReferenceOut


class ReferenceDeleteOut(AuditWriteOut):
    reference_id: UUID
    deleted: bool = True


class McpCommandService:
    def __init__(
        self,
        *,
        work_items: WorkItemService,
        checkpoints: CheckpointService,
        references: ReferenceService,
        policy: McpPolicyService,
        audit: AuditService,
    ) -> None:
        self._work_items = work_items
        self._checkpoints = checkpoints
        self._references = references
        self._policy = policy
        self._audit = audit

    def create_work_item(
        self,
        *,
        title: str,
        goal: str | None = None,
        group_name: str | None = None,
    ) -> WorkItemWriteOut:
        changed = ["title"]
        if goal is not None:
            changed.append("goal")
        if group_name is not None:
            changed.append("group_name")

        def action():
            command = CreateWorkItem(title=title, goal=goal, group_name=group_name)
            access = self._policy.get_policy()
            if access.scope is not McpScope.SELECTED:
                return self._work_items.create(command)

            work_item_id = uuid4()
            self._policy.set_selected_work_item_ids([*access.selected_work_item_ids, work_item_id])
            try:
                return self._work_items.create(command, work_item_id=work_item_id)
            except Exception:
                try:
                    current = self._policy.get_policy()
                    self._policy.set_selected_work_item_ids(
                        [
                            item_id
                            for item_id in current.selected_work_item_ids
                            if item_id != work_item_id
                        ]
                    )
                except Exception:
                    logger.exception("could not remove a reserved MCP Work Item selection")
                raise

        work_item, audit_id = self._execute(
            tool_name="create_work_item",
            operation=McpOperation.CREATE_WORK_ITEM,
            work_item_id=None,
            changed_fields=tuple(changed),
            action=action,
            result_work_item_id=lambda created: created.id,
        )
        return WorkItemWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            work_item=_work_item_out(work_item),
        )

    def update_work_item(
        self,
        work_item_id: UUID,
        *,
        title: str | None = None,
        goal: str | None = None,
        group_name: str | None = None,
    ) -> WorkItemWriteOut:
        changes = {
            key: value
            for key, value in (
                ("title", title),
                ("goal", goal),
                ("group_name", group_name),
            )
            if value is not None
        }

        def action():
            if not changes:
                raise ValidationError("update_work_item", "provide at least one field to change")
            command = UpdateWorkItem.model_validate(changes)
            return self._work_items.update(work_item_id, command)

        work_item, audit_id = self._execute(
            tool_name="update_work_item",
            operation=McpOperation.UPDATE_WORK_ITEM,
            work_item_id=work_item_id,
            changed_fields=tuple(changes),
            action=action,
        )
        return WorkItemWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            work_item=_work_item_out(work_item),
        )

    def save_progress_update(
        self,
        work_item_id: UUID,
        *,
        stopped_at: str,
        next_actions: str,
        completed_work: str | None = None,
        blockers: str | None = None,
        context_summary: str | None = None,
    ) -> CheckpointWriteOut:
        changed = ["stopped_at", "next_actions"]
        for name, value in (
            ("completed_work", completed_work),
            ("blockers", blockers),
            ("context_summary", context_summary),
        ):
            if value is not None:
                changed.append(name)

        def action():
            work_item = self._work_items.get(work_item_id)
            if work_item.status not in (WorkItemStatus.ACTIVE, WorkItemStatus.PAUSED):
                raise ValidationError("status", "resume the work item before saving progress")
            return self._checkpoints.save(
                SaveCheckpoint(
                    work_item_id=work_item_id,
                    stopped_at=stopped_at,
                    next_actions=next_actions,
                    completed_work=completed_work,
                    blockers=blockers,
                    context_summary=context_summary,
                )
            )

        checkpoint, audit_id = self._execute(
            tool_name="save_progress_update",
            operation=McpOperation.SAVE_PROGRESS_UPDATE,
            work_item_id=work_item_id,
            changed_fields=tuple(changed),
            action=action,
        )
        return CheckpointWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            checkpoint=_checkpoint_out(checkpoint),
        )

    def change_work_item_status(
        self,
        work_item_id: UUID,
        status: WorkItemStatus,
    ) -> WorkItemWriteOut:
        def action():
            current = self._work_items.get(work_item_id)
            if status is current.status:
                return current
            if current.needs_confirmation_to_resume:
                raise ValidationError("status", "resume completed or archived work in NextStep")
            if status is WorkItemStatus.ACTIVE:
                return self._work_items.resume(work_item_id)
            return self._work_items.change_status(work_item_id, status)

        work_item, audit_id = self._execute(
            tool_name="change_work_item_status",
            operation=McpOperation.CHANGE_WORK_ITEM_STATUS,
            work_item_id=work_item_id,
            changed_fields=("status",),
            action=action,
        )
        return WorkItemWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            work_item=_work_item_out(work_item),
        )

    def add_reference(
        self,
        work_item_id: UUID,
        *,
        reference_type: ReferenceType,
        label: str,
        target: str,
        checkpoint_id: UUID | None = None,
    ) -> ReferenceWriteOut:
        command = AddReference(
            work_item_id=work_item_id,
            type=reference_type,
            label=label,
            target=target,
            checkpoint_id=checkpoint_id,
        )
        changed = ["type", "label", "target"]
        if checkpoint_id is not None:
            changed.append("checkpoint_id")
        reference, audit_id = self._execute(
            tool_name="add_reference",
            operation=McpOperation.ADD_REFERENCE,
            work_item_id=work_item_id,
            changed_fields=tuple(changed),
            action=lambda: self._references.add(command),
        )
        return ReferenceWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            reference=_reference_out(reference),
        )

    def update_reference(
        self,
        reference_id: UUID,
        *,
        label: str | None = None,
        target: str | None = None,
    ) -> ReferenceWriteOut:
        changes = {
            key: value for key, value in (("label", label), ("target", target)) if value is not None
        }

        reference = self._require_reference(
            reference_id,
            tool_name="update_reference",
            operation=McpOperation.UPDATE_REFERENCE,
            changed_fields=tuple(changes),
        )

        def action():
            if not changes:
                raise ValidationError("update_reference", "provide at least one field to change")
            command = UpdateReference.model_validate(changes)
            return self._references.update(reference_id, command)

        updated, audit_id = self._execute(
            tool_name="update_reference",
            operation=McpOperation.UPDATE_REFERENCE,
            work_item_id=reference.work_item_id,
            changed_fields=tuple(changes),
            action=action,
        )
        return ReferenceWriteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            reference=_reference_out(updated),
        )

    def delete_reference(self, reference_id: UUID) -> ReferenceDeleteOut:
        reference = self._require_reference(
            reference_id,
            tool_name="delete_reference",
            operation=McpOperation.DELETE_REFERENCE,
            changed_fields=(),
        )
        _, audit_id = self._execute(
            tool_name="delete_reference",
            operation=McpOperation.DELETE_REFERENCE,
            work_item_id=reference.work_item_id,
            changed_fields=(),
            action=lambda: self._references.delete(reference_id),
        )
        return ReferenceDeleteOut(
            audit_id=audit_id,
            audit_recorded=audit_id is not None,
            reference_id=reference_id,
        )

    def _require_reference(
        self,
        reference_id: UUID,
        *,
        tool_name: str,
        operation: McpOperation,
        changed_fields: Iterable[str],
    ):
        policy = self._policy.get_write_policy()
        try:
            self._require_allowed(policy, operation, None)
        except AccessDeniedError:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.DENIED,
                work_item_id=None,
                changed_fields=changed_fields,
                error_code="access_denied",
            )
            raise

        try:
            reference = self._references.get(reference_id)
        except NotFoundError:
            if policy.access.scope is McpScope.SELECTED:
                self._record_audit(
                    tool_name=tool_name,
                    operation=operation,
                    outcome=AuditOutcome.DENIED,
                    work_item_id=None,
                    changed_fields=changed_fields,
                    error_code="access_denied",
                )
                raise AccessDeniedError("Reference is not available to MCP.") from None
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.ERROR,
                work_item_id=None,
                changed_fields=changed_fields,
                error_code="not_found",
            )
            raise
        if not policy.access.allows(reference.work_item_id):
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.DENIED,
                work_item_id=None,
                changed_fields=changed_fields,
                error_code="access_denied",
            )
            raise AccessDeniedError("Reference is not available to MCP.")
        return reference

    def _execute(
        self,
        *,
        tool_name: str,
        operation: McpOperation,
        work_item_id: UUID | None,
        changed_fields: Iterable[str],
        action: Callable[[], T],
        result_work_item_id: Callable[[T], UUID | None] | None = None,
    ) -> tuple[T, UUID | None]:
        fields = tuple(changed_fields)
        try:
            policy = self._policy.get_write_policy()
            self._require_allowed(policy, operation, work_item_id)
            result = action()
        except AccessDeniedError:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.DENIED,
                work_item_id=work_item_id,
                changed_fields=fields,
                error_code="access_denied",
            )
            raise
        except ValidationError:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.ERROR,
                work_item_id=work_item_id,
                changed_fields=fields,
                error_code="validation_error",
            )
            raise
        except NotFoundError:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.ERROR,
                work_item_id=work_item_id,
                changed_fields=fields,
                error_code="not_found",
            )
            raise
        except NextStepError:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.ERROR,
                work_item_id=work_item_id,
                changed_fields=fields,
                error_code="domain_error",
            )
            raise
        except Exception:
            self._record_audit(
                tool_name=tool_name,
                operation=operation,
                outcome=AuditOutcome.ERROR,
                work_item_id=work_item_id,
                changed_fields=fields,
                error_code="internal_error",
            )
            raise

        audit_work_item_id = (
            result_work_item_id(result) if result_work_item_id is not None else work_item_id
        )
        audit_id = self._record_audit(
            tool_name=tool_name,
            operation=operation,
            outcome=AuditOutcome.SUCCESS,
            work_item_id=audit_work_item_id,
            changed_fields=fields,
        )
        return result, audit_id

    def _record_audit(
        self,
        *,
        tool_name: str,
        operation: McpOperation,
        outcome: AuditOutcome,
        work_item_id: UUID | None,
        changed_fields: Iterable[str],
        error_code: str | None = None,
    ) -> UUID | None:
        entry_id = uuid4()
        try:
            self._audit.record(
                entry_id=entry_id,
                tool_name=tool_name,
                operation=operation,
                outcome=outcome,
                work_item_id=work_item_id,
                changed_fields=changed_fields,
                error_code=error_code,
            )
        except Exception:
            # Audit is best effort: never turn a successful write into an error
            # just because the local log could not be appended.
            logger.exception("could not write MCP audit log entry")
            return None
        return entry_id

    @staticmethod
    def _require_allowed(
        policy: McpWritePolicy,
        operation: McpOperation,
        work_item_id: UUID | None,
    ) -> None:
        if not policy.access.enabled:
            raise AccessDeniedError("MCP access is disabled in NextStep Settings.")
        if not policy.enabled:
            raise AccessDeniedError("MCP changes are disabled in NextStep Settings.")
        if operation not in policy.operations:
            raise AccessDeniedError(f"MCP is not allowed to {operation.value.replace('_', ' ')}.")
        if work_item_id is not None and not policy.access.allows(work_item_id):
            raise AccessDeniedError("This work item is not shared with MCP.")
