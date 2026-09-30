from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/parse", tags=["parse"])


class ParseFileRequest(BaseModel):
    path: str


def _hex_preview(raw: bytes, limit: int = 4096) -> str:
    chunk = raw[:limit]
    lines: list[str] = []
    for index in range(0, len(chunk), 16):
        part = chunk[index:index + 16]
        hex_part = " ".join(f"{byte:02x}" for byte in part)
        lines.append(f"{index:08x}  {hex_part}")
    if len(raw) > limit:
        lines.append(f"\n... truncated, total bytes: {len(raw)}")
    return "\n".join(lines)


def _parse_text_file(path: Path, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    preview = "\n".join(lines[:120])
    return {
        "mode": "text",
        "line_count": len(lines),
        "preview": preview,
    }


def _parse_dxf(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    entity_hits = {
        "LINE": 0,
        "CIRCLE": 0,
        "ARC": 0,
        "TEXT": 0,
        "DIMENSION": 0,
    }
    for line in lines:
        token = line.strip().upper()
        if token in entity_hits:
            entity_hits[token] += 1
    return {
        "entity_summary": entity_hits,
        "preview": "\n".join(lines[:160]),
    }


def _parse_ipj(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "entries": lines[:80],
        "preview": "\n".join(lines[:120]),
    }


@router.post("/file")
def parse_file(req: ParseFileRequest) -> dict[str, Any]:
    path = Path(req.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    suffix = path.suffix.lower()
    raw = path.read_bytes()
    stat = path.stat()

    result: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "size_bytes": stat.st_size,
        "mode": "binary",
        "summary": {},
        "preview": "",
    }

    if suffix in {".dxf", ".ipj"}:
        text = raw.decode("utf-8", errors="replace")
        result["mode"] = "text"
        result["summary"] = _parse_text_file(path, text)
        result["preview"] = result["summary"]["preview"]
        if suffix == ".dxf":
            result["summary"]["dxf"] = _parse_dxf(text)
        elif suffix == ".ipj":
            result["summary"]["ipj"] = _parse_ipj(text)
        return result

    if suffix in {".ipt", ".iam", ".idw", ".dwg"}:
        result["mode"] = "binary"
        result["summary"] = {
            "binary_type": suffix[1:].upper(),
            "header_ascii": raw[:64].decode("ascii", errors="replace"),
        }
        result["preview"] = _hex_preview(raw)
        return result

    text = raw.decode("utf-8", errors="replace")
    result["mode"] = "text"
    result["summary"] = _parse_text_file(path, text)
    result["preview"] = result["summary"]["preview"]
    return result
