"""Domain errors.

Services raise these errors so the desktop UI and the future MCP server can
share one error contract instead of translating database exceptions.
"""

from __future__ import annotations


class NextStepError(Exception):
    """Base class for all expected NextStep errors."""


class ValidationError(NextStepError):
    """A field value violates a domain rule."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class NotFoundError(NextStepError):
    """A requested entity does not exist."""

    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} not found: {entity_id}")


class ConfirmationRequiredError(NextStepError):
    """The action changes status and needs explicit user confirmation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AccessDeniedError(NextStepError):
    """The caller is not allowed to read the requested local data."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ArchiveError(NextStepError):
    """A backup or export file cannot be created or trusted."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class RestoreRequiresRestartError(ArchiveError):
    """Restore failed after the live database was closed.

    The current data is still on disk, but the running application can no longer
    use its database engine. The UI must close instead of continuing.
    """
