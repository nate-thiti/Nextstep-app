"""Read-only projections exposed to the local MCP server.

The MCP tools call these methods instead of touching SQLite. Every query goes
through the same Core Services the desktop UI uses, so validation, ordering and
access rules stay in one place.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from nextstep.application.checkpoints import CheckpointService
from nextstep.application.mcp_policy import McpAccessPolicy, McpPolicyService
from nextstep.application.resume import ResumeService
from nextstep.application.work_items import WorkItemService, WorkItemSummary
from nextstep.domain.entities import Checkpoint, WorkItem, WorkReference
from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.domain.errors import AccessDeniedError, ValidationError

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class McpModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class WorkItemOut(McpModel):
    id: UUID
    title: str
    status: WorkItemStatus
    goal: str | None
    group: str | None
    created_at: datetime
    updated_at: datetime
    needs_confirmation_to_resume: bool


class WorkItemSummaryOut(McpModel):
    work_item: WorkItemOut
    has_blocker: bool
    latest_checkpoint_id: UUID | None
    latest_checkpoint_at: datetime | None


class WorkItemListOut(McpModel):
    items: list[WorkItemSummaryOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class ReferenceOut(McpModel):
    id: UUID
    type: ReferenceType
    label: str
    target: str
    checkpoint_id: UUID | None
    metadata: dict[str, Any]


class CheckpointOut(McpModel):
    id: UUID
    work_item_id: UUID
    stopped_at: str
    next_actions: str
    completed_work: str | None
    blockers: str | None
    context_summary: str | None
    status_after_save: WorkItemStatus
    created_at: datetime
    updated_at: datetime
    has_blocker: bool


class WorkContextOut(McpModel):
    work_item: WorkItemOut
    latest_checkpoint: CheckpointOut | None
    references: list[ReferenceOut]


class LatestCheckpointOut(McpModel):
    work_item: WorkItemOut
    checkpoint: CheckpointOut | None


class CheckpointSearchHitOut(McpModel):
    work_item_id: UUID
    work_item_title: str
    work_item_status: WorkItemStatus
    checkpoint: CheckpointOut


class CheckpointSearchOut(McpModel):
    items: list[CheckpointSearchHitOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class McpQueryService:
    def __init__(
        self,
        *,
        work_items: WorkItemService,
        checkpoints: CheckpointService,
        resume: ResumeService,
        policy: McpPolicyService,
    ) -> None:
        self._work_items = work_items
        self._checkpoints = checkpoints
        self._resume = resume
        self._policy = policy

    def list_work_items(
        self,
        *,
        status: WorkItemStatus | None = None,
        group_name: str | None = None,
        search: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> WorkItemListOut:
        policy = self._require_enabled()
        _validate_page(limit, offset)

        page = self._work_items.page_summaries(
            status=status,
            group_name=group_name,
            search=search,
            work_item_ids=policy.allowed_work_item_ids(),
            limit=limit,
            offset=offset,
        )
        return WorkItemListOut(
            items=[_summary_out(summary) for summary in page.summaries],
            total=page.total,
            limit=limit,
            offset=offset,
            has_more=page.has_more,
        )

    def get_work_context(self, work_item_id: UUID) -> WorkContextOut:
        self._require_allowed(work_item_id)
        data = self._resume.get(work_item_id)
        return WorkContextOut(
            work_item=_work_item_out(data.work_item),
            latest_checkpoint=(
                _checkpoint_out(data.latest_checkpoint) if data.latest_checkpoint else None
            ),
            references=[_reference_out(reference) for reference in data.references],
        )

    def get_latest_checkpoint(self, work_item_id: UUID) -> LatestCheckpointOut:
        self._require_allowed(work_item_id)
        work_item = self._work_items.get(work_item_id)
        checkpoint = self._checkpoints.get_latest(work_item_id)
        return LatestCheckpointOut(
            work_item=_work_item_out(work_item),
            checkpoint=_checkpoint_out(checkpoint) if checkpoint else None,
        )

    def search_checkpoints(
        self,
        query: str,
        *,
        work_item_id: UUID | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> CheckpointSearchOut:
        policy = self._require_enabled()
        _validate_page(limit, offset)

        if work_item_id is not None:
            self._require_allowed(work_item_id, policy)
            allowed_ids: list[UUID] | None = [work_item_id]
        else:
            allowed_ids = policy.allowed_work_item_ids()

        page = self._checkpoints.search(
            query,
            work_item_ids=allowed_ids,
            limit=limit,
            offset=offset,
        )
        titles = self._work_items.get_many([item.work_item_id for item in page.checkpoints])
        items: list[CheckpointSearchHitOut] = []
        for checkpoint in page.checkpoints:
            work_item = titles.get(checkpoint.work_item_id)
            if work_item is None:
                continue
            items.append(
                CheckpointSearchHitOut(
                    work_item_id=work_item.id,
                    work_item_title=work_item.title,
                    work_item_status=work_item.status,
                    checkpoint=_checkpoint_out(checkpoint),
                )
            )
        return CheckpointSearchOut(
            items=items,
            total=page.total,
            limit=limit,
            offset=offset,
            has_more=page.has_more,
        )

    def _require_enabled(self) -> McpAccessPolicy:
        policy = self._policy.get_policy()
        if not policy.enabled:
            raise AccessDeniedError("MCP access is disabled in NextStep Settings.")
        return policy

    def _require_allowed(
        self,
        work_item_id: UUID,
        policy: McpAccessPolicy | None = None,
    ) -> McpAccessPolicy:
        resolved = policy or self._require_enabled()
        if not resolved.allows(work_item_id):
            raise AccessDeniedError("This work item is not shared with MCP.")
        return resolved


def _validate_page(limit: int, offset: int) -> None:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValidationError("limit", f"must be between 1 and {MAX_PAGE_SIZE}")
    if offset < 0:
        raise ValidationError("offset", "must be 0 or greater")


def _work_item_out(work_item: WorkItem) -> WorkItemOut:
    return WorkItemOut(
        id=work_item.id,
        title=work_item.title,
        status=work_item.status,
        goal=work_item.goal,
        group=work_item.group_name,
        created_at=work_item.created_at,
        updated_at=work_item.updated_at,
        needs_confirmation_to_resume=work_item.needs_confirmation_to_resume,
    )


def _summary_out(summary: WorkItemSummary) -> WorkItemSummaryOut:
    checkpoint = summary.latest_checkpoint
    return WorkItemSummaryOut(
        work_item=_work_item_out(summary.work_item),
        has_blocker=summary.has_blocker,
        latest_checkpoint_id=checkpoint.id if checkpoint else None,
        latest_checkpoint_at=checkpoint.created_at if checkpoint else None,
    )


def _checkpoint_out(checkpoint: Checkpoint) -> CheckpointOut:
    return CheckpointOut(
        id=checkpoint.id,
        work_item_id=checkpoint.work_item_id,
        stopped_at=checkpoint.stopped_at,
        next_actions=checkpoint.next_actions,
        completed_work=checkpoint.completed_work,
        blockers=checkpoint.blockers,
        context_summary=checkpoint.context_summary,
        status_after_save=checkpoint.status_after_save,
        created_at=checkpoint.created_at,
        updated_at=checkpoint.updated_at,
        has_blocker=checkpoint.has_blocker,
    )


def _reference_out(reference: WorkReference) -> ReferenceOut:
    return ReferenceOut(
        id=reference.id,
        type=reference.type,
        label=reference.label,
        target=reference.target,
        checkpoint_id=reference.checkpoint_id,
        metadata=dict(reference.metadata),
    )
