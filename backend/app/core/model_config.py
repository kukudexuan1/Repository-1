"""LLM 端点与模型配置的唯一来源。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_env_loaded = False


class ModelConfigError(RuntimeError):
    """模型配置缺失或不完整。"""


def load_env(*, override: bool = True, force: bool = False) -> bool:
    """加载 backend/.env。幂等；进程内重复调用只生效一次（除非 force）。

    override 默认为 True：`.env` 是本项目声明式的配置来源，应当胜过残留的
    shell/系统环境变量。若确实需要用环境变量覆盖 `.env`（如 CI），显式传
    override=False。
    """
    global _env_loaded
    if _env_loaded and not force:
        return True

    env_path = PROJECT_ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("未安装 python-dotenv，跳过 .env 加载，将直接读取环境变量")
        _env_loaded = True
        return False

    loaded = load_dotenv(env_path, override=override)
    if not loaded:
        logger.warning("未找到或未能加载 .env: %s", env_path)
    _env_loaded = True
    return loaded


def skip_env_file() -> None:
    """声明配置已由调用方备好，后续 load_env 不再读 .env。

    供测试使用：否则 override=True 会用 .env 里的真实凭据覆盖测试值。
    """
    global _env_loaded
    _env_loaded = True


@dataclass(frozen=True)
class ModelSlot:
    """一个模型槽位的生效配置。"""

    name: str
    label: str
    model: str
    api_key: str
    base_url: str

    def describe(self) -> dict[str, str]:
        """脱敏后的配置摘要，可安全写入日志与 HTTP 响应。"""
        return {
            "slot": self.name,
            "label": self.label,
            "model": self.model,
            "endpoint": self.base_url,
            "api_key": mask_secret(self.api_key),
        }


@dataclass(frozen=True)
class _SlotSpec:
    name: str
    label: str
    model_var: str
    key_var: str
    endpoint_var: str
    used_by: str


# 子 Agent 的 key/endpoint 缺失时回落到主模型的同名配置（同一服务商的常见情形），
# 但模型 ID 永不回落 —— 用错模型比报错更难发现。
_SLOT_SPECS: dict[str, _SlotSpec] = {
    "main": _SlotSpec(
        "main", "主设计模型", "DEEPSEEK_MODEL", "DEEPSEEK_API_KEY", "DEEPSEEK_ENDPOINT", "agent_loop"
    ),
    "coder": _SlotSpec(
        "coder", "建模子 Agent", "QWEN_CODER_MODEL", "QWEN_CODER_API_KEY", "QWEN_CODER_ENDPOINT", "modeling_agent"
    ),
    "math": _SlotSpec(
        "math", "仿真子 Agent", "QWEN_MATH_MODEL", "QWEN_MATH_API_KEY", "QWEN_MATH_ENDPOINT", "analysis_agent"
    ),
    "vision": _SlotSpec(
        "vision", "视觉/图纸解析", "QWEN3_VL_PLUS_MODEL", "QWEN3_VL_PLUS_API_KEY", "QWEN3_VL_PLUS_ENDPOINT", "express_tools"
    ),
}


def mask_secret(secret: str) -> str:
    if not secret:
        return "(未设置)"
    if len(secret) <= 12:
        return f"{secret[:3]}***"
    return f"{secret[:6]}...{secret[-4:]}"


def _read(spec: _SlotSpec) -> ModelSlot:
    model = (os.getenv(spec.model_var) or "").strip()
    if not model:
        raise ModelConfigError(
            f"{spec.label}（{spec.used_by}）缺少模型配置：请在 backend/.env 中设置 "
            f"{spec.model_var}。不使用默认值，以免静默调用非预期模型。"
        )

    api_key = (os.getenv(spec.key_var) or os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise ModelConfigError(
            f"{spec.label}（{spec.used_by}）缺少 API key：请设置 {spec.key_var} 或 DEEPSEEK_API_KEY。"
        )

    base_url = (os.getenv(spec.endpoint_var) or os.getenv("DEEPSEEK_ENDPOINT") or "").strip()
    if not base_url:
        raise ModelConfigError(
            f"{spec.label}（{spec.used_by}）缺少 endpoint：请设置 {spec.endpoint_var} 或 DEEPSEEK_ENDPOINT。"
        )

    return ModelSlot(
        name=spec.name, label=spec.label, model=model, api_key=api_key, base_url=base_url
    )


def get_slot(name: str) -> ModelSlot:
    """读取指定槽位的生效配置。配置不全时抛 ModelConfigError。"""
    spec = _SLOT_SPECS.get(name)
    if spec is None:
        raise KeyError(f"未知模型槽位: {name}（可选: {', '.join(_SLOT_SPECS)}）")
    load_env()
    return _read(spec)


def main_slot() -> ModelSlot:
    return get_slot("main")


def coder_slot() -> ModelSlot:
    return get_slot("coder")


def math_slot() -> ModelSlot:
    return get_slot("math")


def vision_slot() -> ModelSlot:
    return get_slot("vision")


def enable_thinking() -> bool:
    load_env()
    return (os.getenv("DEEPSEEK_ENABLE_THINKING", "true") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def reasoning_effort() -> str:
    """DeepSeek reasoning effort for the main model."""
    load_env()
    value = (os.getenv("DEEPSEEK_REASONING_EFFORT", "high") or "").strip().lower()
    if value not in {"low", "high", "max"}:
        raise ModelConfigError(
            "DEEPSEEK_REASONING_EFFORT 必须是 low、high 或 max"
        )
    return value


def describe_all() -> list[dict[str, str]]:
    """全部槽位的脱敏配置摘要；单个槽位配置有误时以 error 字段呈现而不抛出。"""
    load_env()
    rows: list[dict[str, str]] = []
    for spec in _SLOT_SPECS.values():
        try:
            rows.append(_read(spec).describe())
        except ModelConfigError as exc:
            rows.append(
                {
                    "slot": spec.name,
                    "label": spec.label,
                    "model": "(未配置)",
                    "endpoint": os.getenv(spec.endpoint_var, "") or os.getenv("DEEPSEEK_ENDPOINT", ""),
                    "api_key": "(未配置)",
                    "error": str(exc),
                }
            )
    return rows


def log_effective_config() -> None:
    """启动时打印生效的模型配置，便于事后核对某轮对话用的是哪个模型。"""
    for row in describe_all():
        if "error" in row:
            logger.error("模型槽位 %s 配置异常: %s", row["slot"], row["error"])
        else:
            logger.info(
                "模型槽位 %-6s %-14s model=%s endpoint=%s key=%s",
                row["slot"],
                row["label"],
                row["model"],
                row["endpoint"],
                row["api_key"],
            )
