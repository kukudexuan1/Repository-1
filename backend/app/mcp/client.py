"""Persistent stdio client wrapper for a single MCP server.

The connection lifecycle (stdio_client + ClientSession) is held open inside one
dedicated background task. anyio cancel scopes must be exited in the same task
that created them, so entering/exiting these contexts across separate start()/
stop() calls (e.g. via AsyncExitStack) corrupts the scope. Keeping the whole
`async with` block in a single task avoids that entirely.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import MCPServerConfig
from .result import ToolResult, normalize_call_result

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("MCP_LOG_DIR", "./logs")).expanduser()


class MCPClient:
    """Owns one MCP server subprocess and its ClientSession."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: ClientSession | None = None
        self._tools: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._ready: asyncio.Event = asyncio.Event()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._start_error: BaseException | None = None

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def _run(self) -> None:
        env = {**os.environ, **self.config.env}
        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            cwd=self.config.cwd,
            env=env,
        )
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        errlog = open(LOG_DIR / f"mcp-{self.config.name}.log", "a", encoding="utf-8")
        try:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(
                        session.initialize(), timeout=self.config.init_timeout
                    )
                    self._session = session
                    await self._refresh_tools()
                    logger.info(
                        "MCP server '%s' connected with %d tools",
                        self.config.name,
                        len(self._tools),
                    )
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as exc:
            self._start_error = exc
            logger.error("MCP server '%s' run error: %s", self.config.name, exc)
        finally:
            self._session = None
            try:
                errlog.close()
            except Exception:
                pass
            self._ready.set()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._ready = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._start_error = None
        self._task = asyncio.create_task(self._run())
        await self._ready.wait()
        if self._session is None:
            err = self._start_error
            await self.stop()
            raise RuntimeError(
                f"MCP server '{self.config.name}' failed to start: {err}"
            )

    async def _refresh_tools(self) -> None:
        assert self._session is not None
        listed = await self._session.list_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema or {"type": "object", "properties": {}},
            }
            for t in listed.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        if self._session is None:
            return ToolResult(success=False, error=f"MCP server '{self.config.name}' not connected")
        async with self._lock:
            try:
                raw = await asyncio.wait_for(
                    self._session.call_tool(name, arguments or {}),
                    timeout=self.config.call_timeout,
                )
            except asyncio.TimeoutError:
                return ToolResult(success=False, error=f"调用超时: {name} ({self.config.call_timeout}s)")
            except Exception as exc:
                return ToolResult(success=False, error=f"调用失败: {name}: {exc}")
        return normalize_call_result(raw)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=15)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("MCP server '%s' stop timed out, cancelled", self.config.name)
            except Exception as exc:
                logger.warning("Error stopping MCP server '%s': %s", self.config.name, exc)
        self._task = None
        self._session = None
        self._tools = []
