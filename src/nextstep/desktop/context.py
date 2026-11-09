"""Desktop-facing re-export of the shared composition root.

The real wiring lives in :mod:`nextstep.bootstrap` so the local MCP server can
build the same Core Services without importing PySide6.
"""

from __future__ import annotations

from nextstep.bootstrap import (
    RESTORE_MARKER_NAME,
    RESTORE_MARKER_VERSION,
    AppContext,
    build_context,
)

__all__ = [
    "RESTORE_MARKER_NAME",
    "RESTORE_MARKER_VERSION",
    "AppContext",
    "build_context",
]
