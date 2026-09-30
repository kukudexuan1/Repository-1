"""受限计算脚本执行器（子进程入口，不要直接导入）。

从 stdin 读取 {"script", "inputs", "expected_outputs"}，在受限命名空间中执行脚本，
把结果以 JSON 写到 stdout。放在子进程里执行是为了能真正强杀超时任务。
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout

_ALLOWED_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
    "format", "int", "isinstance", "len", "list", "map", "max", "min", "pow",
    "print", "range", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "True", "False", "None",
}


def _build_namespace(inputs: dict) -> dict:
    import math

    import numpy as np
    import sympy as sp
    from scipy import integrate, interpolate, optimize

    builtins_src = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
    safe_builtins = {k: v for k, v in builtins_src.items() if k in _ALLOWED_BUILTINS}

    namespace = {
        "__builtins__": safe_builtins,
        "math": math,
        "np": np,
        "numpy": np,
        "sp": sp,
        "sympy": sp,
        "optimize": optimize,
        "integrate": integrate,
        "interpolate": interpolate,
        "outputs": {},
    }
    namespace.update(inputs)
    return namespace


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        json.dump({"ok": False, "error": f"输入不是合法 JSON: {exc}"}, sys.stdout)
        return 1

    script = payload.get("script", "")
    inputs = payload.get("inputs", {}) or {}
    expected = payload.get("expected_outputs", []) or []

    namespace = _build_namespace(inputs)
    buffer = io.StringIO()

    try:
        with redirect_stdout(buffer):
            exec(compile(script, "<design_calculation>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001 - 需要把错误回传给模型自行修正
        json.dump(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "stdout": buffer.getvalue()[-2000:],
            },
            sys.stdout,
        )
        return 0

    collected: dict[str, float] = {}
    declared = namespace.get("outputs")
    if isinstance(declared, dict):
        for key, value in declared.items():
            num = _to_float(value)
            if num is not None:
                collected[str(key)] = num
    for key in expected:
        if key in collected:
            continue
        num = _to_float(namespace.get(key))
        if num is not None:
            collected[key] = num

    json.dump(
        {"ok": True, "outputs": collected, "stdout": buffer.getvalue()[-2000:]},
        sys.stdout,
    )
    return 0


def _to_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            import sympy as sp

            return float(sp.N(value))
        except Exception:  # noqa: BLE001
            return None


if __name__ == "__main__":
    sys.exit(main())
