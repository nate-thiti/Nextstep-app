"""Enumerations shared by the domain and the persistence layer."""

from __future__ import annotations

from enum import StrEnum


class WorkItemStatus(StrEnum):
    """Lifecycle status of a Work Item (MVP_SPEC section 7.1)."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ReferenceType(StrEnum):
    """Supported reference kinds (MVP_SPEC section 8)."""

    FILE = "file"
    FOLDER = "folder"
    URL = "url"
    GIT_REPOSITORY = "git_repository"


class McpOperation(StrEnum):
    """Write capabilities that can be granted to the local MCP server."""

    CREATE_WORK_ITEM = "create_work_item"
    UPDATE_WORK_ITEM = "update_work_item"
    SAVE_PROGRESS_UPDATE = "save_progress_update"
    CHANGE_WORK_ITEM_STATUS = "change_work_item_status"
    ADD_REFERENCE = "add_reference"
    UPDATE_REFERENCE = "update_reference"
    DELETE_REFERENCE = "delete_reference"


class AuditOutcome(StrEnum):
    """Result recorded for one MCP write attempt."""

    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"
