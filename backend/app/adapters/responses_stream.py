"""Shared parsing / folding for OpenAI-compatible Responses API SSE streams."""

from __future__ import annotations

import json
from typing import Any


def parse_responses_sse_line(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw or raw.startswith(":"):
        return None
    data_str = raw[5:].lstrip() if raw.startswith("data:") else raw
    if data_str == "[DONE]":
        return None
    if not data_str:
        return None
    try:
        obj = json.loads(data_str)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if "type" not in obj and isinstance(obj.get("data"), dict):
        inner = obj["data"]
        if isinstance(inner, dict) and inner.get("type"):
            return inner
    return obj


def assistant_text_from_response_object(resp: dict[str, Any]) -> str:
    output = resp.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            parts: list[str] = []
            for piece in content:
                if isinstance(piece, dict) and piece.get("type") == "output_text":
                    t = piece.get("text", "")
                    if isinstance(t, str) and t:
                        parts.append(t)
            if parts:
                return "".join(parts).strip()
    ot = resp.get("output_text")
    if isinstance(ot, str) and ot.strip():
        return ot.strip()
    return ""


def merge_stream_authoritative_text(full_text: str, text: str) -> tuple[str, str]:
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    text = text.strip()
    if not text:
        return (full_text, "")
    if not full_text:
        return (text, text)
    if text.startswith(full_text):
        return (text, text[len(full_text) :])
    if full_text == text:
        return (full_text, "")
    return (text, "")


def fold_responses_output_text(chunk: dict[str, Any], full_text: str) -> tuple[str, str]:
    ctype = chunk.get("type")
    if ctype == "response.output_text.delta":
        d = chunk.get("delta", "")
        if not isinstance(d, str):
            d = str(d) if d is not None else ""
        merged = full_text + d
        return (merged, d)
    if ctype == "response.output_text.done":
        return merge_stream_authoritative_text(full_text, chunk.get("text", ""))
    if ctype == "response.content_part.done":
        part = chunk.get("part")
        if isinstance(part, dict):
            return merge_stream_authoritative_text(full_text, part.get("text", ""))
        return (full_text, "")
    if ctype == "response.output_item.done":
        item = chunk.get("item")
        if isinstance(item, dict) and item.get("type") == "message":
            text = assistant_text_from_response_object({"output": [item]})
            if text:
                return merge_stream_authoritative_text(full_text, text)
        return (full_text, "")
    if ctype == "response.completed":
        resp = chunk.get("response")
        if isinstance(resp, dict):
            text = assistant_text_from_response_object(resp)
            if text:
                return merge_stream_authoritative_text(full_text, text)
        return (full_text, "")
    return (full_text, "")


def fold_chat_completion_delta(chunk: dict[str, Any], full_text: str) -> tuple[str, str]:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return (full_text, "")
    delta = choices[0].get("delta") or {}
    if not isinstance(delta, dict):
        return (full_text, "")
    content = delta.get("content")
    raw = ""
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if isinstance(p.get("text"), str):
                    parts.append(p["text"])
                elif p.get("type") == "text" and isinstance(p.get("text"), str):
                    parts.append(p["text"])
        raw = "".join(parts)
    if not raw:
        return (full_text, "")
    return (full_text + raw, raw)
