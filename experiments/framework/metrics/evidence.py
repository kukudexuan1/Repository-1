"""
evidence.py — E3 / E12 参数证据链与报告一致性指标。

ECR  证据完整率       = N_complete / N_all
TCR  计算可复核率     = N_reproducible_calculations / N_all_calculations
UAR  无依据参数率     = N_unsupported_parameters / N_all_parameters
DCR  报告数字一致率   = N_consistent_report_values / N_report_numeric_values

所有函数接受纯 Python dict/list，不依赖 backend 内部对象。
"""

from __future__ import annotations

from typing import Any


def _bool(val: Any) -> bool:
    if val is None:
        return False
    return bool(val)


# ---------------------------------------------------------------------------
# 单参数判断辅助
# ---------------------------------------------------------------------------

def _param_is_complete(param: dict) -> bool:
    """
    协议 E3：参数完整性要求同时满足：
      - has_source=True
      - source_matches=True
      - has_calc_or_std=True
    """
    return (
        _bool(param.get("has_source"))
        and _bool(param.get("source_matches"))
        and _bool(param.get("has_calc_or_std"))
    )


def _param_is_unsupported(param: dict) -> bool:
    """无依据参数：没有来源 OR 没有计算/标准依据。"""
    return not _bool(param.get("has_source")) or not _bool(param.get("has_calc_or_std"))


# ---------------------------------------------------------------------------
# ECR / UAR
# ---------------------------------------------------------------------------

def evidence_completeness_rate(parameters: list[dict]) -> dict[str, Any]:
    """
    ECR = N_complete / N_all

    parameters 格式（来自人工标注或系统台账）：
    [{"param_id": "d1", "has_source": true, "source_matches": true,
      "has_calc_or_std": true, "has_design_reason": true, ...}, ...]
    """
    n_all = len(parameters)
    if n_all == 0:
        return {"ECR": 0.0, "n_complete": 0, "n_all": 0}
    n_complete = sum(1 for p in parameters if _param_is_complete(p))
    return {
        "ECR": round(n_complete / n_all, 4),
        "n_complete": n_complete,
        "n_all": n_all,
    }


def unsupported_parameter_rate(parameters: list[dict]) -> dict[str, Any]:
    """UAR = N_unsupported / N_all"""
    n_all = len(parameters)
    if n_all == 0:
        return {"UAR": 0.0, "n_unsupported": 0, "n_all": 0}
    n_unsupported = sum(1 for p in parameters if _param_is_unsupported(p))
    return {
        "UAR": round(n_unsupported / n_all, 4),
        "n_unsupported": n_unsupported,
        "n_all": n_all,
    }


# ---------------------------------------------------------------------------
# TCR
# ---------------------------------------------------------------------------

def _calc_is_reproducible(calc: dict) -> bool:
    """
    计算记录可复核：同时具备公式引用、输入参数列表和数值结果。
    协议 E3：「能从报告追溯到原始输入」。
    """
    return (
        bool(calc.get("formula_id") or calc.get("formula_expr"))
        and bool(calc.get("inputs"))
        and calc.get("result") is not None
    )


def calculation_reproducibility_rate(calculations: list[dict]) -> dict[str, Any]:
    """
    TCR = N_reproducible_calculations / N_all_calculations

    calculations 格式：
    [{"calc_id": "c001", "formula_id": "F_bending",
      "inputs": {...}, "result": 123.4, "unit": "MPa", ...}, ...]
    """
    n_all = len(calculations)
    if n_all == 0:
        return {"TCR": 0.0, "n_reproducible": 0, "n_all": 0}
    n_repr = sum(1 for c in calculations if _calc_is_reproducible(c))
    return {
        "TCR": round(n_repr / n_all, 4),
        "n_reproducible": n_repr,
        "n_all": n_all,
    }


# ---------------------------------------------------------------------------
# DCR
# ---------------------------------------------------------------------------

def report_digit_consistency_rate(
    report_values: list[dict],
    ledger_values: dict[str, Any],
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """
    DCR = N_consistent_report_values / N_report_numeric_values

    report_values 格式：
    [{"param_id": "d1", "value_in_report": 45.0, "unit": "mm"}, ...]

    ledger_values 格式：
    {"d1": {"value": 45.0, "unit": "mm", "status": "frozen"}, ...}

    若参数在台账中不存在，视为不一致。
    只比较数值，不比较单位（单位转换超出此函数范围）。
    """
    n_all = len(report_values)
    if n_all == 0:
        return {"DCR": 0.0, "n_consistent": 0, "n_all": 0, "inconsistencies": []}

    n_consistent = 0
    inconsistencies = []

    for rv in report_values:
        pid = rv.get("param_id", "")
        report_val = rv.get("value_in_report")
        ledger_entry = ledger_values.get(pid)

        if ledger_entry is None:
            inconsistencies.append({"param_id": pid, "reason": "not_in_ledger"})
            continue

        ledger_val = ledger_entry.get("value")
        if report_val is None or ledger_val is None:
            inconsistencies.append({"param_id": pid, "reason": "null_value"})
            continue

        try:
            if abs(float(report_val) - float(ledger_val)) <= tolerance:
                n_consistent += 1
            else:
                inconsistencies.append({
                    "param_id": pid,
                    "report_val": report_val,
                    "ledger_val": ledger_val,
                    "diff": abs(float(report_val) - float(ledger_val)),
                    "reason": "value_mismatch",
                })
        except (TypeError, ValueError):
            if str(report_val) == str(ledger_val):
                n_consistent += 1
            else:
                inconsistencies.append({
                    "param_id": pid,
                    "report_val": report_val,
                    "ledger_val": ledger_val,
                    "reason": "type_mismatch",
                })

    return {
        "DCR": round(n_consistent / n_all, 4),
        "n_consistent": n_consistent,
        "n_all": n_all,
        "inconsistencies": inconsistencies,
    }


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def compute_evidence_metrics(
    parameters: list[dict],
    calculations: list[dict],
    report_values: list[dict] | None = None,
    ledger_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """一次性计算 ECR / TCR / UAR / DCR（DCR 需要提供 report 和 ledger）。"""
    result: dict[str, Any] = {}
    result.update(evidence_completeness_rate(parameters))
    result.update(unsupported_parameter_rate(parameters))
    result.update(calculation_reproducibility_rate(calculations))
    if report_values is not None and ledger_values is not None:
        result.update(report_digit_consistency_rate(report_values, ledger_values))
    return result
