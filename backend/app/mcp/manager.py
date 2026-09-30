"""Singleton manager for all MCP server connections."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .client import MCPClient
from .config import MCPServerConfig, load_ansys_config, load_mcpcad_config
from .result import ToolResult

logger = logging.getLogger(__name__)

MCPCAD = "mcp-cad"
ANSYS = "ansys-workbench"


class MCPManager:
    """Owns the mcp-cad and ansys-workbench clients."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._configs: dict[str, MCPServerConfig] = {}

    def _register(self, config: MCPServerConfig) -> None:
        self._configs[config.name] = config
        self._clients[config.name] = MCPClient(config)

    async def start(self) -> None:
        if not self._clients:
            self._register(load_mcpcad_config())
            self._register(load_ansys_config())

        for name, client in self._clients.items():
            if not client.config.enabled:
                logger.info("MCP server '%s' disabled, skipping", name)
                continue
            try:
                await client.start()
            except Exception as exc:
                logger.error("Failed to start MCP server '%s': %s", name, exc)

    async def stop(self) -> None:
        await asyncio.gather(*(c.stop() for c in self._clients.values()), return_exceptions=True)

    def get(self, server: str) -> MCPClient | None:
        return self._clients.get(server)

    def tools(self, server: str) -> list[dict[str, Any]]:
        client = self._clients.get(server)
        return client.tools if client else []

    def is_connected(self, server: str) -> bool:
        client = self._clients.get(server)
        return bool(client and client.connected)

    async def call(self, server: str, tool: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        client = self._clients.get(server)
        if client is None:
            return ToolResult(success=False, error=f"未知 MCP server: {server}")
        return await client.call_tool(tool, arguments)


_manager: MCPManager | None = None


def get_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
