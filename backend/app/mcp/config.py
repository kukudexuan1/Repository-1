"""Configuration for MCP server subprocesses (mcp-cad, ansys-workbench)."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    init_timeout: float = 60.0
    call_timeout: float = 600.0


def _split(value: str) -> list[str]:
    if not value.strip():
        return []
    return shlex.split(value, posix=(os.name != "nt"))


def load_mcpcad_config() -> MCPServerConfig:
    """mcp-cad (.NET / Inventor). Default: dotnet run from source."""
    command = os.getenv("MCPCAD_COMMAND", "dotnet").strip()
    args_env = os.getenv("MCPCAD_ARGS", "run --project src/McpCad.Server")
    cwd = os.getenv("MCPCAD_CWD", "").strip() or None
    enabled = os.getenv("MCPCAD_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    return MCPServerConfig(
        name="mcp-cad",
        command=command,
        args=_split(args_env),
        cwd=cwd,
        enabled=enabled,
        init_timeout=float(os.getenv("MCPCAD_INIT_TIMEOUT", "90")),
        call_timeout=float(os.getenv("MCPCAD_CALL_TIMEOUT", "600")),
    )


def load_ansys_config() -> MCPServerConfig:
    """ansys-workbench-mcp (Python / FastMCP)."""
    command = os.getenv("ANSYS_MCP_COMMAND", "python").strip()
    args_env = os.getenv("ANSYS_MCP_ARGS", "mcp_server.py")
    cwd = os.getenv("ANSYS_MCP_CWD", "").strip() or None
    enabled = os.getenv("ANSYS_MCP_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    env: dict[str, str] = {}
    for key in (
        "ANSYS_WORKBENCH_MCP_HOME",
        "ANSYS_WORKBENCH_MCP_SCRATCH",
        "ANSYS_RUNWB2",
        "ANSYS_MECHANICAL",
        "ANSYS_MAPDL",
        "ANSYS_FLUENT",
        "ANSYS_CFX_SOLVE",
        "ANSYS_CFX_PRE",
        "ANSYS_BRIDGE_START_WAIT",
        "ANSYS_BRIDGE_TIMEOUT",
        "ANSYS_LOG_MARKER_WAIT",
    ):
        val = os.getenv(key)
        if val:
            env[key] = val
    return MCPServerConfig(
        name="ansys-workbench",
        command=command,
        args=_split(args_env),
        cwd=cwd,
        env=env,
        enabled=enabled,
        init_timeout=float(os.getenv("ANSYS_MCP_INIT_TIMEOUT", "60")),
        call_timeout=float(os.getenv("ANSYS_MCP_CALL_TIMEOUT", "3600")),
    )
