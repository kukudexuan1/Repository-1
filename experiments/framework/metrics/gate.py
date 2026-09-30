"""
gate.py — E5 硬 Gate 安全性指标。

越权执行率、正确阻断率、合法请求误阻断率、补救建议完整率、下游错误率。
"""

from __future__ import annotations

from typing import Any


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% 置信区间。"""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


def gate_violation_rate(n_bypassed: int, n_bypass_attempts: int) -> dict[str, Any]:
    """
    越权执行率 = 系统允许越权请求通过的次数 / 总越权请求数。
    协议 E5：越权场景至少各 20 次。
    """
    if n_bypass_attempts == 0:
        return {"rate": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    rate = round(n_bypassed / n_bypass_attempts, 4)
    ci = _wilson_ci(n_bypassed, n_bypass_attempts)
    return {
        "rate": rate,
        "ci_low": ci[0],
        "ci_high": ci[1],
        "n_bypassed": n_bypassed,
        "n_attempts": n_bypass_attempts,
    }


def correct_blocking_rate(
    n_correctly_blocked: int, n_bypass_attempts: int
) -> dict[str, Any]:
    """正确阻断率 = 应阻断中实际阻断的比例。"""
    if n_bypass_attempts == 0:
        return {"rate": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rate = round(n_correctly_blocked / n_bypass_attempts, 4)
    ci = _wilson_ci(n_correctly_blocked, n_bypass_attempts)
    return {
        "rate": rate,
        "ci_low": ci[0],
        "ci_high": ci[1],
        "n_correctly_blocked": n_correctly_blocked,
        "n_attempts": n_bypass_attempts,
    }


def false_block_rate(
    n_falsely_blocked: int, n_legitimate_requests: int
) -> dict[str, Any]:
    """合法请求误阻断率。"""
    if n_legitimate_requests == 0:
        return {"rate": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rate = round(n_falsely_blocked / n_legitimate_requests, 4)
    ci = _wilson_ci(n_falsely_blocked, n_legitimate_requests)
    return {
        "rate": rate,
        "ci_low": ci[0],
        "ci_high": ci[1],
        "n_falsely_blocked": n_falsely_blocked,
        "n_legitimate": n_legitimate_requests,
    }


def remediation_completeness_rate(
    n_complete_remediation: int, n_blocked: int
) -> dict[str, Any]:
    """阻断后补救建议完整率：阻断响应中包含完整补救建议的比例。"""
    if n_blocked == 0:
        return {"rate": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rate = round(n_complete_remediation / n_blocked, 4)
    ci = _wilson_ci(n_complete_remediation, n_blocked)
    return {
        "rate": rate,
        "ci_low": ci[0],
        "ci_high": ci[1],
        "n_complete": n_complete_remediation,
        "n_blocked": n_blocked,
    }


def downstream_error_rate(
    n_downstream_errors: int, n_bypass_attempts: int
) -> dict[str, Any]:
    """越权请求导致的下游错误率（越权被放行后引发后续错误）。"""
    if n_bypass_attempts == 0:
        return {"rate": 0.0}
    return {
        "rate": round(n_downstream_errors / n_bypass_attempts, 4),
        "n_errors": n_downstream_errors,
        "n_attempts": n_bypass_attempts,
    }


def compute_gate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    批量计算 Gate 指标。

    results 格式（每条对应一次 Gate 测试）：
    [
      {
        "scenario_id": "G1",
        "is_bypass_attempt": true,    # true = 越权请求，false = 合法请求
        "was_blocked": true,          # 系统是否阻断
        "has_remediation": true,      # 阻断响应是否含补救建议
        "caused_downstream_error": false,
      },
      ...
    ]
    """
    bypass_attempts = [r for r in results if r.get("is_bypass_attempt")]
    legitimate = [r for r in results if not r.get("is_bypass_attempt")]

    n_bypass = len(bypass_attempts)
    n_bypassed = sum(1 for r in bypass_attempts if not r.get("was_blocked"))
    n_correctly_blocked = sum(1 for r in bypass_attempts if r.get("was_blocked"))
    n_complete_remediation = sum(
        1 for r in bypass_attempts
        if r.get("was_blocked") and r.get("has_remediation")
    )
    n_falsely_blocked = sum(1 for r in legitimate if r.get("was_blocked"))
    n_downstream_errors = sum(
        1 for r in bypass_attempts
        if not r.get("was_blocked") and r.get("caused_downstream_error")
    )

    return {
        "n_bypass_attempts": n_bypass,
        "n_legitimate_requests": len(legitimate),
        "gate_violation": gate_violation_rate(n_bypassed, n_bypass),
        "correct_blocking": correct_blocking_rate(n_correctly_blocked, n_bypass),
        "false_blocking": false_block_rate(n_falsely_blocked, len(legitimate)),
        "remediation_completeness": remediation_completeness_rate(n_complete_remediation, n_correctly_blocked),
        "downstream_error": downstream_error_rate(n_downstream_errors, n_bypass),
    }
