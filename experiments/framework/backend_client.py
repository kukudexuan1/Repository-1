"""
backend_client.py — 与 backend 解耦的同步 HTTP 客户端。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .condition import Condition, ConditionConfig, get_condition
from .run_manager import load_config


def _cfg() -> dict:
    return load_config()


class BackendClient:
    """跨轮次复用同一 session 的 backend 客户端。"""

    def __init__(
        self,
        condition: Condition | str,
        session_id: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        cfg = _cfg()
        self.condition_cfg: ConditionConfig = get_condition(condition)
        self.base_url = (base_url or cfg["backend"]["url"]).rstrip("/")
        read_timeout = float(cfg["backend"].get("timeout_read", 300))
        connect_timeout = float(cfg["backend"].get("timeout_connect", 10))
        self.timeout = httpx.Timeout(timeout or read_timeout, connect=connect_timeout)
        self.session_id = session_id
        self._tool_trace: list[dict[str, Any]] = []

    def create_session(self) -> str:
        response = httpx.post(
            f"{self.base_url}/api/sessions",
            json={"target_cad": "inventor", "mode": "design"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        self.session_id = str(response.json()["session_id"])
        return self.session_id

    def list_sessions(self, limit: int = 1000) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/api/sessions",
            params={"limit": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("session_id 未设置")
        response = httpx.get(f"{self.base_url}/api/sessions/{sid}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def clone_session(self, session_id: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/sessions/{session_id}/clone",
            timeout=self.timeout,
        )
        response.raise_for_status()
        self.session_id = str(response.json()["session_id"])
        return self.session_id

    def delete_session(self, session_id: str | None = None) -> None:
        sid = session_id or self.session_id
        if sid:
            httpx.delete(f"{self.base_url}/api/sessions/{sid}", timeout=self.timeout)

    def run(
        self,
        user_prompt: str,
        capture_state: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self.session_id is None:
            self.create_session()

        state_before = self.get_session() if capture_state else {}
        headers = self.condition_cfg.to_request_headers()
        headers.update(extra_headers or {})
        payload = {"session_id": self.session_id, "user_prompt": user_prompt}
        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/workflow/run",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        elapsed = time.perf_counter() - started
        response.raise_for_status()
        result = response.json()
        state_after = self.get_session() if capture_state else {}
        self._tool_trace.append(
            {
                "prompt": user_prompt,
                "condition": self.condition_cfg.name,
                "session_id": self.session_id,
                "elapsed_s": round(elapsed, 3),
                "design_stage": result.get("design_stage"),
                "tool_calls_made": result.get("tool_calls_made", []),
                "tool_events": result.get("tool_events", []),
                "awaiting_decision": result.get("awaiting_decision", False),
                "decision_id": result.get("decision_id", ""),
                "reply_length": len(result.get("reply", "")),
            }
        )
        return {
            "response": result,
            "state_before": state_before,
            "state_after": state_after,
            "elapsed_s": elapsed,
        }

    def get_tool_trace(self) -> list[dict[str, Any]]:
        return list(self._tool_trace)

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:  # noqa: BLE001
            return False


class BextClient:
    """保留 B-EXT 所需的最小客户端接口。"""

    def __init__(self) -> None:
        cfg = _cfg().get("bext", {})
        self.endpoint = cfg.get("endpoint", "")
        self.api_key = os.environ.get(cfg.get("api_key_env", "BEXT_API_KEY"), "")
        self.model = cfg.get("model", "deepseek-v4-pro")
        self.temperature = float(cfg.get("temperature", 0.0))
        self.system_prompt = cfg.get("system_prompt", "你是一名经验丰富的机械设计工程师。")
        self.max_tokens = int(cfg.get("max_tokens", 8192))
        self._history: list[dict[str, str]] = []

    def reset(self) -> None:
        self._history = []

    def chat(self, user_message: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.endpoint)
        messages = [{"role": "system", "content": self.system_prompt}, *self._history]
        messages.append({"role": "user", "content": user_message})
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        reply = response.choices[0].message.content or ""
        self._history.extend(
            [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}]
        )
        return {
            "reply": reply,
            "usage": response.usage.model_dump() if response.usage else {},
            "elapsed_s": round(time.perf_counter() - started, 3),
            "model": self.model,
        }
