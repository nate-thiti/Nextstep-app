"""Smoke-test packaged desktop and MCP executables without touching user data."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "list_work_items",
    "get_work_context",
    "get_latest_checkpoint",
    "search_checkpoints",
    "create_work_item",
    "update_work_item",
    "save_progress_update",
    "change_work_item_status",
    "add_reference",
    "update_reference",
    "delete_reference",
}


def smoke_desktop(desktop_exe: Path, data_root: Path) -> None:
    print("Starting packaged desktop...", flush=True)
    env = os.environ.copy()
    env["NEXTSTEP_DATA_DIR"] = str(data_root)
    env["QT_QPA_PLATFORM"] = "offscreen"
    process = subprocess.Popen(desktop_exe, env=env)
    database = data_root / "data" / "nextstep.db"
    required = {"work_items", "checkpoints", "work_references", "app_settings"}
    try:
        # Cold starts of freshly compiled/signature-less Windows binaries can be
        # delayed by antivirus scanning, especially on the first launch.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Desktop executable exited with code {process.returncode}")
            if database.exists():
                try:
                    with sqlite3.connect(database) as connection:
                        tables = {
                            row[0]
                            for row in connection.execute(
                                "SELECT name FROM sqlite_master WHERE type = 'table'"
                            ).fetchall()
                        }
                    if required <= tables:
                        break
                except sqlite3.OperationalError:
                    pass
            time.sleep(0.25)
        else:
            raise RuntimeError("Desktop executable did not finish creating its database")
        print("Packaged desktop database is ready.", flush=True)
    finally:
        print("Stopping packaged desktop...", flush=True)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        print("Packaged desktop stopped.", flush=True)


async def smoke_mcp(mcp_exe: Path, data_root: Path) -> None:
    print("Starting packaged MCP server...", flush=True)
    env = os.environ.copy()
    env["NEXTSTEP_DATA_DIR"] = str(data_root)
    parameters = StdioServerParameters(
        command=str(mcp_exe),
        args=[],
        env=env,
    )
    async with asyncio.timeout(60):
        async with stdio_client(parameters) as streams, ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    if names != EXPECTED_TOOLS:
        raise RuntimeError(f"Packaged MCP tools differ: {sorted(names)}")
    print("Packaged MCP tools are ready.", flush=True)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    desktop_exe = project_root / "dist" / "NextStep" / "NextStep.exe"
    mcp_exe = project_root / "dist" / "nextstep-mcp.exe"
    if not desktop_exe.exists() or not mcp_exe.exists():
        raise RuntimeError("Build the packaged executables before running the smoke test")

    root = project_root / ".tmp-package-smoke" / f"run-{uuid4().hex}"
    root.mkdir(exist_ok=True)
    smoke_desktop(desktop_exe, root / "desktop")
    asyncio.run(smoke_mcp(mcp_exe, root / "mcp"))
    print("Packaged desktop and MCP smoke tests passed.")


if __name__ == "__main__":
    main()
