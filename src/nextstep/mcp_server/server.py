"""Local read and permission-gated write MCP tools for NextStep.

The server exposes local work context to an AI client through the same
application services the desktop app uses. Audit entries never contain
checkpoint text, goals or reference URLs.
"""

from __future__ import annotations

import logging
from typing import NoReturn
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nextstep import __version__
from nextstep.application.mcp_commands import (
    CheckpointWriteOut,
    McpCommandService,
    ReferenceDeleteOut,
    ReferenceWriteOut,
    WorkItemWriteOut,
)
from nextstep.application.mcp_queries import (
    DEFAULT_PAGE_SIZE,
    CheckpointSearchOut,
    LatestCheckpointOut,
    McpQueryService,
    WorkContextOut,
    WorkItemListOut,
)
from nextstep.domain.enums import ReferenceType, WorkItemStatus
from nextstep.domain.errors import NextStepError

logger = logging.getLogger(__name__)

SERVER_NAME = "NextStep"
SERVER_INSTRUCTIONS = (
    "Read and update the user's local NextStep work context. "
    "Use list_work_items to discover shared work, get_work_context to resume an "
    "item, and search_checkpoints to find earlier context. Write tools are only "
    "available when the user grants the matching capability in NextStep Settings. "
    "Permanent Work Item deletion is not available through MCP."
)

READ_TOOL_NAMES = (
    "list_work_items",
    "get_work_context",
    "get_latest_checkpoint",
    "search_checkpoints",
)

WRITE_TOOL_NAMES = (
    "create_work_item",
    "update_work_item",
    "save_progress_update",
    "change_work_item_status",
    "add_reference",
    "update_reference",
    "delete_reference",
)

TOOL_NAMES = READ_TOOL_NAMES + WRITE_TOOL_NAMES


def build_server(queries: McpQueryService, commands: McpCommandService) -> MCPServer:
    """Build the MCP server around a query service.

    The policy is read on every call, so changing it in the desktop app takes
    effect without restarting the MCP server.
    """
    server = MCPServer(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        version=__version__,
    )

    @server.tool()
    def list_work_items(
        status: str | None = None,
        group: str | None = None,
        query: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> WorkItemListOut:
        """List Work Items shared with MCP, newest updates first.

        Args:
            status: Optional filter: active, paused, completed or archived.
            group: Optional exact group name.
            query: Optional text search across titles, goals, checkpoints and references.
            limit: Page size, 1 to 100.
            offset: Number of matching items to skip.
        """
        logger.info("MCP tool called: list_work_items")
        try:
            return queries.list_work_items(
                status=_parse_status(status),
                group_name=_clean(group),
                search=_clean(query),
                limit=limit,
                offset=offset,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def get_work_context(work_item_id: UUID) -> WorkContextOut:
        """Return a Work Item, its latest checkpoint and its resume references.

        Args:
            work_item_id: UUID of a Work Item shared with MCP.
        """
        logger.info("MCP tool called: get_work_context")
        try:
            return queries.get_work_context(work_item_id)
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def get_latest_checkpoint(work_item_id: UUID) -> LatestCheckpointOut:
        """Return the most recent checkpoint for one shared Work Item.

        Args:
            work_item_id: UUID of a Work Item shared with MCP.
        """
        logger.info("MCP tool called: get_latest_checkpoint")
        try:
            return queries.get_latest_checkpoint(work_item_id)
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def search_checkpoints(
        query: str,
        work_item_id: UUID | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> CheckpointSearchOut:
        """Search checkpoint text across shared Work Items, newest first.

        Args:
            query: Text to find in completed work, stopped-at notes, blockers,
                next actions or context summaries.
            work_item_id: Optional UUID to search a single shared Work Item.
            limit: Page size, 1 to 100.
            offset: Number of matching checkpoints to skip.
        """
        logger.info("MCP tool called: search_checkpoints")
        try:
            return queries.search_checkpoints(
                query,
                work_item_id=work_item_id,
                limit=limit,
                offset=offset,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def create_work_item(
        title: str,
        goal: str | None = None,
        group: str | None = None,
    ) -> WorkItemWriteOut:
        """Create a Work Item. Requires the create_work_item capability.

        Args:
            title: Required Work Item title.
            goal: Optional goal or outcome.
            group: Optional group name.
        """
        logger.info("MCP tool called: create_work_item")
        try:
            return commands.create_work_item(
                title=title,
                goal=goal,
                group_name=_clean(group),
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def update_work_item(
        work_item_id: UUID,
        title: str | None = None,
        goal: str | None = None,
        group: str | None = None,
    ) -> WorkItemWriteOut:
        """Update title, goal or group on a shared Work Item.

        Omitted fields are left unchanged. Pass an empty string to clear the
        optional goal or group.

        Args:
            work_item_id: UUID of a shared Work Item.
            title: New title, or omit to keep the current one.
            goal: New goal, empty string to clear, or omit to keep it.
            group: New group, empty string to clear, or omit to keep it.
        """
        logger.info("MCP tool called: update_work_item")
        try:
            return commands.update_work_item(
                work_item_id,
                title=title,
                goal=goal,
                group_name=group,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def save_progress_update(
        work_item_id: UUID,
        stopped_at: str,
        next_actions: str,
        completed_work: str | None = None,
        blockers: str | None = None,
        context_summary: str | None = None,
    ) -> CheckpointWriteOut:
        """Append a progress update to an active or paused shared Work Item.

        Progress updates never change the Work Item status.

        Args:
            work_item_id: UUID of a shared Work Item.
            stopped_at: Where work stopped.
            next_actions: What to do next.
            completed_work: Optional work completed.
            blockers: Optional blockers.
            context_summary: Optional longer context.
        """
        logger.info("MCP tool called: save_progress_update")
        try:
            return commands.save_progress_update(
                work_item_id,
                stopped_at=stopped_at,
                next_actions=next_actions,
                completed_work=completed_work,
                blockers=blockers,
                context_summary=context_summary,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def change_work_item_status(work_item_id: UUID, status: str) -> WorkItemWriteOut:
        """Pause, finish or archive a shared Work Item.

        Completed and archived work must be resumed in the desktop app.

        Args:
            work_item_id: UUID of a shared Work Item.
            status: active, paused, completed or archived.
        """
        logger.info("MCP tool called: change_work_item_status")
        parsed = _parse_status(status)
        if parsed is None:
            raise ToolError("Status is required.")
        try:
            return commands.change_work_item_status(work_item_id, parsed)
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def add_reference(
        work_item_id: UUID,
        type: str,
        label: str,
        target: str,
        checkpoint_id: UUID | None = None,
    ) -> ReferenceWriteOut:
        """Attach a file, folder, URL or Git repository reference to shared work.

        Args:
            work_item_id: UUID of a shared Work Item.
            type: file, folder, url or git_repository.
            label: Short display label.
            target: Absolute path or http(s) URL.
            checkpoint_id: Optional progress update to attach the reference to.
        """
        logger.info("MCP tool called: add_reference")
        try:
            return commands.add_reference(
                work_item_id,
                reference_type=_parse_reference_type(type),
                label=label,
                target=target,
                checkpoint_id=checkpoint_id,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def update_reference(
        reference_id: UUID,
        label: str | None = None,
        target: str | None = None,
    ) -> ReferenceWriteOut:
        """Update a reference label or target. Omitted fields stay unchanged.

        Args:
            reference_id: UUID of a reference on shared work.
            label: New label, or omit to keep it.
            target: New absolute path or URL, or omit to keep it.
        """
        logger.info("MCP tool called: update_reference")
        try:
            return commands.update_reference(
                reference_id,
                label=label,
                target=target,
            )
        except NextStepError as error:
            _raise_tool_error(error)

    @server.tool()
    def delete_reference(reference_id: UUID) -> ReferenceDeleteOut:
        """Delete one reference. Requires the delete_reference capability.

        Args:
            reference_id: UUID of a reference on shared work.
        """
        logger.info("MCP tool called: delete_reference")
        try:
            return commands.delete_reference(reference_id)
        except NextStepError as error:
            _raise_tool_error(error)

    return server


def _parse_status(value: str | None) -> WorkItemStatus | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return WorkItemStatus(text.lower())
    except ValueError:
        raise ToolError(
            "Unknown status. Use one of: active, paused, completed, archived."
        ) from None


def _parse_reference_type(value: str) -> ReferenceType:
    text = value.strip().lower()
    try:
        return ReferenceType(text)
    except ValueError:
        raise ToolError(
            "Unknown reference type. Use one of: file, folder, url, git_repository."
        ) from None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _raise_tool_error(error: NextStepError) -> NoReturn:
    raise ToolError(str(error)) from error
