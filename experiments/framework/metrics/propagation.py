"""
propagation.py — E4 依赖失效传播指标。

IR   失效识别召回率  = |PredictedStale ∩ GoldStale| / |GoldStale|
ORR  过期结果泄漏率  = N_stale_values_used_downstream / N_GoldStale
BR   阻断率          = 1 - ORR
IRE  增量重算效率    = 1 - N_incremental_recalculations / N_full_recalculations
"""

from __future__ import annotations

from typing import Any


def invalidation_recall(predicted_stale: set[str], gold_stale: set[str]) -> float:
    """IR = |PredictedStale ∩ GoldStale| / |GoldStale|"""
    if not gold_stale:
        return 1.0
    tp = len(predicted_stale & gold_stale)
    return round(tp / len(gold_stale), 4)


def invalidation_precision(predicted_stale: set[str], gold_stale: set[str]) -> float:
    """误报率补充：precision = |TP| / |PredictedStale|"""
    if not predicted_stale:
        return 1.0
    tp = len(predicted_stale & gold_stale)
    return round(tp / len(predicted_stale), 4)


def outdated_result_rate(
    stale_values_used_downstream: int, n_gold_stale: int
) -> float:
    """ORR = N_stale_values_used_downstream / N_GoldStale"""
    if n_gold_stale == 0:
        return 0.0
    return round(stale_values_used_downstream / n_gold_stale, 4)


def blocking_rate(orr: float) -> float:
    """BR = 1 - ORR"""
    return round(1.0 - orr, 4)


def incremental_recalculation_efficiency(
    n_incremental: int, n_full: int
) -> float:
    """
    IRE = 1 - N_incremental_recalculations / N_full_recalculations

    IRE > 0 表示增量比全量少算了一些节点（高效）。
    IRE = 0 表示增量与全量相同（无优化）。
    IRE < 0 表示增量多算了（出现误报，不应发生）。
    """
    if n_full == 0:
        return 0.0
    return round(1.0 - n_incremental / n_full, 4)


def compute_propagation_metrics(run_result: dict[str, Any]) -> dict[str, Any]:
    """
    从单次运行结果计算所有 E4 指标。

    run_result 格式：
    {
      "predicted_stale_params": [...],
      "predicted_stale_calcs":  [...],
      "gold_stale_params":      [...],
      "gold_stale_calcs":       [...],
      "stale_params_used_downstream": int,
      "stale_calcs_used_downstream":  int,
      "n_incremental_recalculations": int,
      "n_full_recalculations":        int,
      "recovery_time_s":              float,
      "tool_calls_after_change":      int,
      "human_interventions":          int,
    }
    """
    pred_p = set(run_result.get("predicted_stale_params", []))
    pred_c = set(run_result.get("predicted_stale_calcs", []))
    gold_p = set(run_result.get("gold_stale_params", []))
    gold_c = set(run_result.get("gold_stale_calcs", []))

    predicted_stale = pred_p | pred_c
    gold_stale = gold_p | gold_c

    stale_used = (
        run_result.get("stale_params_used_downstream", 0)
        + run_result.get("stale_calcs_used_downstream", 0)
    )
    n_gold = len(gold_stale)

    ir = invalidation_recall(predicted_stale, gold_stale)
    prec = invalidation_precision(predicted_stale, gold_stale)
    orr = outdated_result_rate(stale_used, n_gold)
    br = blocking_rate(orr)
    ire = incremental_recalculation_efficiency(
        run_result.get("n_incremental_recalculations", 0),
        run_result.get("n_full_recalculations", 0),
    )

    return {
        "IR": ir,
        "invalidation_precision": prec,
        "ORR": orr,
        "BR": br,
        "IRE": ire,
        "n_gold_stale": n_gold,
        "n_predicted_stale": len(predicted_stale),
        "stale_used_downstream": stale_used,
        "recovery_time_s": run_result.get("recovery_time_s", None),
        "tool_calls_after_change": run_result.get("tool_calls_after_change", None),
        "human_interventions": run_result.get("human_interventions", 0),
        # 协议硬性要求：P 条件 ORR 必须为 0
        "orr_violation": orr > 0,
    }
