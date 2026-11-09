"""Client-specific setup snippets for the local stdio MCP server."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class McpClientGuide:
    key: str
    label: str
    location: str
    steps: str
    configuration: str

    @property
    def copyable(self) -> bool:
        return bool(self.configuration)


def resolve_mcp_command() -> Path:
    """Find the MCP entry point installed beside the running Python/app executable."""
    sibling = Path(sys.executable).with_name("nextstep-mcp.exe")
    if sibling.exists():
        return sibling.resolve()
    discovered = shutil.which("nextstep-mcp") or shutil.which("nextstep-mcp.exe")
    return Path(discovered).resolve() if discovered else sibling.resolve()


def build_mcp_client_guides(command: Path) -> list[McpClientGuide]:
    command_text = str(command)
    portable = json.dumps(
        {
            "mcpServers": {
                "nextstep": {
                    "command": command_text,
                    "args": [],
                }
            }
        },
        indent=2,
        ensure_ascii=False,
    )
    vscode = json.dumps(
        {
            "servers": {
                "nextstep": {
                    "type": "stdio",
                    "command": command_text,
                    "args": [],
                }
            }
        },
        indent=2,
        ensure_ascii=False,
    )
    codex = f"[mcp_servers.nextstep]\ncommand = {json.dumps(command_text)}\nargs = []\n"
    quoted_command = f'"{command_text}"'
    return [
        McpClientGuide(
            "codex",
            "Codex CLI / IDE",
            "%USERPROFILE%\\.codex\\config.toml",
            "Merge this TOML block into the config, restart Codex, then run `codex mcp list`.",
            codex,
        ),
        McpClientGuide(
            "claude_desktop",
            "Claude Desktop",
            "%APPDATA%\\Claude\\claude_desktop_config.json",
            "Merge the `nextstep` entry into `mcpServers`, save, then restart Claude Desktop.",
            portable,
        ),
        McpClientGuide(
            "claude_code",
            "Claude Code",
            "Project root: .mcp.json",
            "Save or merge this project config, restart Claude Code, then run `/mcp` to verify.",
            portable,
        ),
        McpClientGuide(
            "cursor",
            "Cursor",
            "%USERPROFILE%\\.cursor\\mcp.json",
            "Merge the server entry, restart Cursor, then enable NextStep under Available Tools.",
            portable,
        ),
        McpClientGuide(
            "vscode",
            "VS Code / GitHub Copilot",
            "Workspace: .vscode\\mcp.json",
            "Merge this VS Code-format entry, run `MCP: List Servers`, then start "
            "and trust NextStep.",
            vscode,
        ),
        McpClientGuide(
            "gemini",
            "Gemini CLI",
            "%USERPROFILE%\\.gemini\\settings.json",
            "Merge the server into settings.json, restart Gemini CLI, then run `gemini mcp list`.",
            portable,
        ),
        McpClientGuide(
            "windsurf",
            "Windsurf",
            "%USERPROFILE%\\.codeium\\windsurf\\mcp_config.json",
            "Merge the server entry, save the file, then restart Windsurf to discover its tools.",
            portable,
        ),
        McpClientGuide(
            "generic",
            "Other stdio MCP client",
            "Use the client’s local MCP configuration",
            "Set transport to stdio, use this executable as `command`, and pass no arguments.",
            portable,
        ),
        McpClientGuide(
            "cli_command",
            "Command only",
            "Use in a client that asks for a server command",
            "Paste this executable path as the stdio command. Do not add shell redirection.",
            quoted_command,
        ),
        McpClientGuide(
            "web_clients",
            "ChatGPT / Claude.ai web",
            "Not available through a local stdio config",
            "Web clients cannot launch this executable on your PC. NextStep needs a supported "
            "desktop client, or a future remote/tunnel transport.",
            "",
        ),
    ]
