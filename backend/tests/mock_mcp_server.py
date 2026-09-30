"""A minimal real MCP stdio server used as a fixture for client-layer tests.

Run via `python -m tests.mock_mcp_server` style (as a subprocess). It exposes
two tools so MCPClient/list_tools/call_tool can be exercised without Inventor
or ANSYS being installed.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-mcp")


@mcp.tool()
def echo(text: str = "") -> str:
    """Echo back the given text (returns JSON-ish string like ansys)."""
    return '{"ok": true, "echo": "' + text + '"}'


@mcp.tool()
def add(a: float = 0.0, b: float = 0.0) -> str:
    """Add two numbers."""
    return '{"ok": true, "sum": ' + str(a + b) + "}"


if __name__ == "__main__":
    mcp.run()
