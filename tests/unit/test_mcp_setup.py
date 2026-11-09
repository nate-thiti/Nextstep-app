import json
from pathlib import Path

from nextstep.application.mcp_setup import build_mcp_client_guides


def test_mcp_guides_generate_client_specific_formats() -> None:
    command = Path(r"D:\NextStep App\nextstep-mcp.exe")
    guides = {guide.key: guide for guide in build_mcp_client_guides(command)}

    assert {
        "codex",
        "claude_desktop",
        "claude_code",
        "cursor",
        "vscode",
        "gemini",
        "windsurf",
        "generic",
        "web_clients",
    } <= guides.keys()
    portable = json.loads(guides["cursor"].configuration)
    assert portable["mcpServers"]["nextstep"]["command"] == str(command)
    vscode = json.loads(guides["vscode"].configuration)
    assert vscode["servers"]["nextstep"]["type"] == "stdio"
    assert "[mcp_servers.nextstep]" in guides["codex"].configuration
    assert guides["web_clients"].copyable is False
