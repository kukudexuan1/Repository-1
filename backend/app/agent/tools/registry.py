"""主设计模型的工具注册表。"""

from __future__ import annotations

import copy
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from pydantic import BaseModel, ValidationError

from app.schemas.decision import PendingDecision
from app.schemas.session_state import SessionState

logger = logging.getLogger(__name__)


class ToolLayer:
    KNOWLEDGE = "knowledge"
    COMPUTE = "compute"
    LEDGER = "ledger"
    INTERACTION = "interaction"
    EXPRESSION = "expression"
    DELIVERY = "delivery"


class ToolInterrupt(Exception):
    """工具请求中断 agent loop，等待用户答复。"""

    def __init__(self, decision: PendingDecision):
        super().__init__(decision.question)
        self.decision = decision


class ToolRefusal(Exception):
    """工具因门控或前置条件不满足而拒绝执行。

    这不是异常错误，而是要回传给模型的结构化反馈，让它明白为什么不能这么做。
    """

    def __init__(self, reason: str, *, remedy: str = "", details: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.remedy = remedy
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": "refused", "reason": self.reason}
        if self.remedy:
            out["remedy"] = self.remedy
        if self.details:
            out["details"] = self.details
        return out


@dataclass
class ToolContext:
    """工具执行上下文。"""

    session: SessionState
    stream: Callable[[str, str], None] | None = None
    tool_call_id: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def say(self, text: str, channel: str = "system") -> None:
        if self.stream:
            self.stream(channel, text)


def hard_gate_enabled(ctx: ToolContext) -> bool:
    """Return whether code-level workflow gates are active for this request."""
    return bool(ctx.extras.get("experiment_flags", {}).get("gate_enabled", True))


Handler = Callable[[ToolContext, BaseModel], Awaitable[dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler
    layer: str = ToolLayer.COMPUTE
    interrupts: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": flatten_json_schema(self.args_model.model_json_schema()),
            },
        }


_REGISTRY: dict[str, ToolSpec] = {}


def register(
    name: str,
    *,
    description: str,
    args_model: type[BaseModel],
    layer: str = ToolLayer.COMPUTE,
    interrupts: bool = False,
) -> Callable[[Handler], Handler]:
    """把一个 async 函数注册为主设计模型可调用的工具。"""

    def decorator(fn: Handler) -> Handler:
        if name in _REGISTRY:
            raise RuntimeError(f"工具名重复注册: {name}")
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"工具 {name} 的 handler 必须是 async 函数")
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            args_model=args_model,
            handler=fn,
            layer=layer,
            interrupts=interrupts,
        )
        return fn

    return decorator


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def build_openai_tools(
    layers: Iterable[str] | None = None,
    allowed_tools: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """生成传给 LLM 的 tools 参数。

    allowed_tools=None   → 不限制（P 或无条件头时）
    allowed_tools=frozenset() → 不提供任何工具（B0）
    allowed_tools={...}  → 只提供白名单内的工具
    layers               → 在名单基础上进一步按层过滤（已有调用兼容）
    """
    layer_filter = set(layers) if layers else None
    return [
        spec.openai_schema()
        for spec in _REGISTRY.values()
        if (allowed_tools is None or spec.name in allowed_tools)
        and (layer_filter is None or spec.layer in layer_filter)
    ]


async def dispatch(
    name: str,
    raw_arguments: str | dict[str, Any],
    ctx: ToolContext,
    allowed_tools: frozenset[str] | None = None,
) -> dict[str, Any]:
    """校验入参并执行工具。

    allowed_tools=None   → 不限制
    allowed_tools=frozenset() → 所有工具均被封锁（B0）
    allowed_tools={...}  → 仅允许白名单内的工具，其余返回 refused

    ToolInterrupt 会向上抛给 agent loop；其余异常一律转成结构化错误返回给模型，
    避免单个工具失败导致整轮对话中断。
    """
    # 白名单检查：实验条件下屏蔽超出范围的工具
    if allowed_tools is not None and name not in allowed_tools:
        return {
            "status": "refused",
            "reason": (
                f"工具 '{name}' 在当前实验条件下不可用。"
                "该工具已被实验框架封锁以模拟消融条件，这不是工程错误，"
                "请基于当前可用的工具继续完成任务。"
            ),
            "allowed_tools": sorted(allowed_tools),
        }

    spec = _REGISTRY.get(name)
    if spec is None:
        return {
            "status": "error",
            "error": f"未知工具: {name}",
            "available_tools": sorted(_REGISTRY.keys()),
        }

    if isinstance(raw_arguments, str):
        try:
            payload = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"工具参数不是合法 JSON: {exc}"}
    else:
        payload = raw_arguments or {}

    try:
        args = spec.args_model.model_validate(payload)
    except ValidationError as exc:
        return {
            "status": "error",
            "error": "入参校验失败，请按 schema 修正后重试",
            "violations": _format_validation_error(exc),
        }

    try:
        return await spec.handler(ctx, args)
    except ToolInterrupt:
        raise
    except ToolRefusal as exc:
        return exc.to_dict()
    except Exception as exc:  # noqa: BLE001 - 工具错误必须回传给模型自行修正
        logger.exception("工具 %s 执行失败", name)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _format_validation_error(exc: ValidationError) -> list[dict[str, Any]]:
    out = []
    for err in exc.errors():
        out.append(
            {
                "field": ".".join(str(p) for p in err.get("loc", ())),
                "problem": err.get("msg", ""),
            }
        )
    return out


# ---------------------------------------------------------------------------
# JSON Schema 展平：把 Pydantic 生成的 $defs/$ref 内联，兼容各家 function calling
# ---------------------------------------------------------------------------

_MAX_DEPTH = 12
_NOISE_KEYS = {"title", "additionalProperties"}


def flatten_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs", {})
    resolved = _walk(copy.deepcopy(schema), defs, 0)
    resolved.pop("$defs", None)
    resolved.setdefault("type", "object")
    resolved.setdefault("properties", {})
    return resolved


def _walk(node: Any, defs: dict[str, Any], depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return {"type": "object"}
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node.pop("$ref")
            key = ref.rsplit("/", 1)[-1]
            target = copy.deepcopy(defs.get(key, {}))
            target.update(node)
            return _walk(target, defs, depth + 1)
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$defs":
                continue
            if key in _NOISE_KEYS and depth > 0:
                continue
            out[key] = _walk(value, defs, depth + 1)
        return _simplify_optional(out)
    if isinstance(node, list):
        return [_walk(item, defs, depth + 1) for item in node]
    return node


def _simplify_optional(node: dict[str, Any]) -> dict[str, Any]:
    """把 Optional[X] 生成的 anyOf:[X, null] 压成 X，减少模型困惑。"""
    any_of = node.get("anyOf")
    if not isinstance(any_of, list):
        return node
    non_null = [b for b in any_of if isinstance(b, dict) and b.get("type") != "null"]
    if len(non_null) != 1 or len(non_null) == len(any_of):
        return node
    merged = dict(non_null[0])
    for key, value in node.items():
        if key != "anyOf" and key not in merged:
            merged[key] = value
    return merged
