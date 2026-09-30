"""Normalize heterogeneous MCP tool results into a uniform structure.

mcp-cad returns structured dicts (with an error contract).
ansys-workbench returns strings (JSON on success, free text like "Error: ..." on failure).
This module folds both into a single ToolResult.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    error: str = ""
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "success" if self.success else "error",
            "data": self.data,
            "text": self.text,
            "error": self.error,
        }


def _looks_like_error_dict(d: dict[str, Any]) -> tuple[bool, str]:
    # mcp-cad error contract: {"error": "..."} or {"success": false}
    if d.get("error"):
        return True, str(d.get("error"))
    if d.get("success") is False:
        return True, str(d.get("error") or d.get("message") or "operation failed")
    # ansys batch contract: {"ok": false, "error": "..."}
    if d.get("ok") is False:
        return True, str(d.get("error") or "operation failed")
    return False, ""


def _parse_text(text: str) -> ToolResult:
    stripped = text.strip()
    # ansys free-text failure
    if stripped.startswith("Error:") or stripped.startswith("Workbench bridge"):
        return ToolResult(success=False, text=stripped, error=stripped, raw=text)
    # try JSON (ansys success path is json.dumps)
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return ToolResult(success=True, text=stripped, raw=text)
    if isinstance(obj, dict):
        is_err, msg = _looks_like_error_dict(obj)
        return ToolResult(success=not is_err, data=obj, error=msg, raw=text)
    return ToolResult(success=True, data={"value": obj}, text=stripped, raw=text)


def normalize_call_result(result: Any) -> ToolResult:
    """Accept an mcp.types.CallToolResult and fold its content into ToolResult."""
    is_error = bool(getattr(result, "isError", False))
    content = getattr(result, "content", None)

    if content is None:
        return ToolResult(success=not is_error, raw=result)

    texts: list[str] = []
    structured: dict[str, Any] | None = None

    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text":
            texts.append(getattr(block, "text", ""))
        elif btype == "image":
            structured = structured or {}
            structured["image_base64"] = getattr(block, "data", "")
            structured["mime_type"] = getattr(block, "mimeType", "image/png")

    # Prefer text-block parsing: both ansys (str) and mcp-cad emit JSON as text.
    joined = "\n".join(t for t in texts if t)
    if joined:
        parsed = _parse_text(joined)
        if structured:
            parsed.data.update(structured)
        if is_error:
            parsed.success = False
            if not parsed.error:
                parsed.error = parsed.text or "tool reported error"
        return parsed

    # Fallback to structuredContent; FastMCP wraps scalar returns as {"result": value}.
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict) and sc:
        payload: dict[str, Any] = sc
        if set(sc.keys()) == {"result"}:
            inner = sc["result"]
            if isinstance(inner, str):
                parsed = _parse_text(inner)
                if structured:
                    parsed.data.update(structured)
                if is_error:
                    parsed.success = False
                return parsed
            if isinstance(inner, dict):
                payload = inner
        is_err, msg = _looks_like_error_dict(payload)
        merged = dict(payload)
        if structured:
            merged.update(structured)
        return ToolResult(success=not (is_error or is_err), data=merged, error=msg, raw=result)

    if structured:
        return ToolResult(success=not is_error, data=structured, raw=result)
    return ToolResult(success=not is_error, raw=result)
