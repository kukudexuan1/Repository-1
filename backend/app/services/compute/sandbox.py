"""非标计算的沙箱执行器。

公式库覆盖不到的计算（参数扫描、非线性求根、数值积分、符号推导）走这里：
主设计模型给出脚本，在受限子进程中执行 sympy/numpy/scipy，结果同样包装成
CalculationRecord，保证即使是临时计算也留下可追溯的记录。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from app.schemas.calculation_record import CalcEngine, CalculationRecord
from app.schemas.common import Quantity

logger = logging.getLogger(__name__)

RUNNER = Path(__file__).with_name("_sandbox_runner.py")
DEFAULT_TIMEOUT = float(os.getenv("CALC_SANDBOX_TIMEOUT", "30"))
MAX_SCRIPT_CHARS = 8000

# 明显越界的写法直接拒绝，不等到运行期
_FORBIDDEN = (
    "import os", "import sys", "import subprocess", "import socket", "import shutil",
    "import requests", "import httpx", "import pathlib", "open(", "__import__",
    "eval(", "exec(", "compile(", "globals(", "locals(", "getattr(", "setattr(",
    "__class__", "__subclasses__", "__mro__", "__builtins__",
)


class SandboxError(RuntimeError):
    pass


def _preflight(script: str) -> None:
    if not script.strip():
        raise SandboxError("脚本为空")
    if len(script) > MAX_SCRIPT_CHARS:
        raise SandboxError(f"脚本过长（>{MAX_SCRIPT_CHARS} 字符），请拆分计算步骤")
    lowered = script.lower()
    hits = [kw for kw in _FORBIDDEN if kw in lowered]
    if hits:
        raise SandboxError(
            f"脚本包含禁止的写法 {hits}。沙箱只允许纯计算，"
            "可用 math / np / sp / optimize / integrate / interpolate，无需 import"
        )


async def run_script(
    script: str,
    *,
    record_id: str,
    title: str,
    inputs: dict[str, Quantity] | None = None,
    expected_outputs: list[str] | None = None,
    output_units: dict[str, str] | None = None,
    source: str = "",
    criterion: str = "",
    depends_on: list[str] | None = None,
    timeout: float | None = None,
) -> CalculationRecord:
    """在沙箱中执行计算脚本并返回计算记录。"""
    _preflight(script)

    inputs = inputs or {}
    payload = {
        "script": script,
        "inputs": {name: qty.value for name, qty in inputs.items()},
        "expected_outputs": expected_outputs or [],
    }

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(RUNNER),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(payload).encode("utf-8")),
            timeout=timeout or DEFAULT_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise SandboxError(
            f"计算超时（>{timeout or DEFAULT_TIMEOUT:.0f}s）。请简化脚本或缩小扫描范围"
        ) from exc

    if not stdout:
        detail = (stderr or b"").decode("utf-8", errors="replace")[-800:]
        raise SandboxError(f"沙箱无输出，可能缺少依赖：{detail}")

    try:
        result = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise SandboxError(f"沙箱返回非 JSON: {exc}") from exc

    if not result.get("ok"):
        raise SandboxError(
            f"脚本执行失败：{result.get('error', '未知错误')}"
            + (f"\n脚本输出：{result['stdout']}" if result.get("stdout") else "")
        )

    raw_outputs = result.get("outputs") or {}
    if not raw_outputs:
        raise SandboxError(
            "脚本没有产出任何结果。请把结论写入 outputs 字典，"
            "例如 outputs['L10h'] = 64200.0"
        )

    units = output_units or {}
    results = {
        name: Quantity(value=float(value), unit=units.get(name, ""))
        for name, value in raw_outputs.items()
    }

    substitution = "；".join(f"{k}={v.render()}" for k, v in inputs.items())
    engine = CalcEngine.SCIPY if _looks_numeric(script) else CalcEngine.SYMPY

    return CalculationRecord(
        record_id=record_id,
        title=title,
        expression="（沙箱脚本，见 script 字段）",
        inputs=inputs,
        substitution=substitution,
        result=results,
        criterion=criterion,
        source=source or "沙箱数值计算",
        engine=engine,
        depends_on=depends_on or [],
        script=script,
        notes=(result.get("stdout") or "").strip()[:500],
    )


def _looks_numeric(script: str) -> bool:
    return any(kw in script for kw in ("optimize", "integrate", "np.", "numpy"))


def sandbox_available() -> bool:
    return RUNNER.exists()
