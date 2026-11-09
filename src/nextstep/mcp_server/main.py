"""Entry point for the local MCP server (stdio transport)."""

from __future__ import annotations

import logging

from nextstep.bootstrap import build_context
from nextstep.infrastructure.logging_setup import configure_logging
from nextstep.infrastructure.paths import DataPaths
from nextstep.mcp_server.server import build_server

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    del argv
    paths = DataPaths.resolve().ensure()
    configure_logging(paths.logs_dir)
    logger.info("starting local MCP server")

    try:
        context = build_context(paths)
    except Exception:
        logger.exception("MCP server could not open the NextStep database")
        return 1

    try:
        server = build_server(context.mcp_queries, context.mcp_commands)
        server.run("stdio")
    finally:
        context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
