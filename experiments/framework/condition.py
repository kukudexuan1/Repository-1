"""
condition.py — 实验条件枚举与配置。

Condition 枚举对应协议 §4 的六种条件（B_EXT / B0–B4 / P）。
每种条件通过 ConditionConfig 描述需要向 backend 传递的开关，
以及 B_EXT 的直接 API 调用标志。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Condition(str, Enum):
    B_EXT = "B_EXT"
    B0 = "B0"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"
    P = "P"
    E5_C1 = "E5_C1"
    E5_C2 = "E5_C2"


class ConditionConfig:
    """从 config/conditions.yaml 加载的单条件配置。"""

    def __init__(self, name: str, raw: dict) -> None:
        self.name = name
        self.label: str = raw.get("label", name)
        self.description: str = raw.get("description", "")
        self.backend_bypass: bool = raw.get("backend_bypass", False)
        tools = raw.get("tools_enabled", [])
        self.tools_enabled: list[str] | str = tools  # "__all__" 或具体列表
        self.evidence_required: bool = raw.get("evidence_required", False)
        self.gate_enabled: bool = raw.get("gate_enabled", False)
        self.propagation_enabled: bool = raw.get("propagation_enabled", False)
        self.interrupt_recovery: bool = raw.get("interrupt_recovery", False)

    def to_request_headers(self) -> dict[str, str]:
        """
        生成发给 backend 的请求头。
        backend 目前尚未实现条件路由，头部预留供后续集成：
          X-Experiment-Condition: P
          X-Gate-Enabled: true
          X-Propagation-Enabled: true
          X-Evidence-Required: true
        """
        tools_val = (
            "__all__"
            if self.tools_enabled == "__all__"
            else ",".join(self.tools_enabled)
        )
        return {
            "X-Experiment-Condition": self.name,
            "X-Gate-Enabled": str(self.gate_enabled).lower(),
            "X-Propagation-Enabled": str(self.propagation_enabled).lower(),
            "X-Evidence-Required": str(self.evidence_required).lower(),
            "X-Tools-Enabled": tools_val,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.name,
            "label": self.label,
            "backend_bypass": self.backend_bypass,
            "tools_enabled": self.tools_enabled,
            "evidence_required": self.evidence_required,
            "gate_enabled": self.gate_enabled,
            "propagation_enabled": self.propagation_enabled,
            "interrupt_recovery": self.interrupt_recovery,
        }


_registry: dict[str, ConditionConfig] | None = None


def _load_registry() -> dict[str, ConditionConfig]:
    global _registry
    if _registry is not None:
        return _registry
    cfg_path = Path(__file__).resolve().parents[1] / "config" / "conditions.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    _registry = {
        name: ConditionConfig(name, data)
        for name, data in raw.get("conditions", {}).items()
    }
    return _registry


def get_condition(cond: Condition | str) -> ConditionConfig:
    """按名称获取条件配置，不存在时抛出 KeyError。"""
    registry = _load_registry()
    key = cond.value if isinstance(cond, Condition) else str(cond)
    if key not in registry:
        raise KeyError(f"未知条件: {key}，可用: {list(registry.keys())}")
    return registry[key]


def all_conditions() -> list[ConditionConfig]:
    return list(_load_registry().values())
