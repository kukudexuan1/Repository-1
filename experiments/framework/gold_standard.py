"""
gold_standard.py — E4 依赖失效传播实验的金标准受影响集合计算。

金标准须由机械工程专家手工标注，再与自动脚本结果计算 Cohen's kappa。
本模块提供：
  1. 从手工标注文件加载金标准集合
  2. 与系统预测集合计算 kappa / 召回率 / 精确率
  3. kappa < 0.8 时发出警告（协议要求返工标注）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gold_standard(annotation_path: str | Path) -> dict[str, set[str]]:
    """
    从专家标注 JSON 文件加载金标准受影响参数集合。

    标注文件格式：
    {
      "task_id": "G_003",
      "change": "input_power",
      "gold_stale_params": ["T1", "T2", "sigma_H", "sigma_F", "d1", "b"],
      "gold_stale_calcs":  ["calc_001", "calc_003", "calc_007"],
      "annotator": "annotator_A",
      "notes": "..."
    }

    返回 {"params": set(...), "calcs": set(...)}
    """
    path = Path(annotation_path)
    if not path.exists():
        raise FileNotFoundError(f"标注文件不存在: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # 多条标注合并（用于两名标注者各自文件已 merge 的情况）
        params: set[str] = set()
        calcs: set[str] = set()
        for item in data:
            params.update(item.get("gold_stale_params", []))
            calcs.update(item.get("gold_stale_calcs", []))
        return {"params": params, "calcs": calcs}

    return {
        "params": set(data.get("gold_stale_params", [])),
        "calcs": set(data.get("gold_stale_calcs", [])),
    }


def compute_set_metrics(
    predicted: set[str], gold: set[str]
) -> dict[str, float]:
    """
    计算预测集合与金标准集合的精确率、召回率、F1。

    协议 E4：IR = |PredictedStale ∩ GoldStale| / |GoldStale|
    """
    if not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}

    tp = len(predicted & gold)
    fp = len(predicted - gold)
    fn = len(gold - predicted)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def cohen_kappa_binary(
    annotator_a: list[int], annotator_b: list[int]
) -> float:
    """
    计算两名标注者在二值标签（0/1）上的 Cohen's kappa。

    协议规定 kappa < 0.8 须返工标注。
    """
    if len(annotator_a) != len(annotator_b):
        raise ValueError("两名标注者的标注数量不一致")
    n = len(annotator_a)
    if n == 0:
        return 0.0

    agree = sum(a == b for a, b in zip(annotator_a, annotator_b))
    p_o = agree / n

    # 边际概率
    p_a1 = sum(annotator_a) / n
    p_b1 = sum(annotator_b) / n
    p_e = p_a1 * p_b1 + (1 - p_a1) * (1 - p_b1)

    if p_e >= 1.0:
        return 1.0
    return round((p_o - p_e) / (1 - p_e), 4)


def merge_two_annotators(
    path_a: str | Path,
    path_b: str | Path,
    threshold: float = 0.8,
) -> dict[str, Any]:
    """
    合并两名标注者对同一任务的受影响集合标注，计算 kappa。
    如果 kappa < threshold，返回 needs_review=True（不自动合并）。

    返回：
    {
      "kappa": float,
      "needs_review": bool,
      "merged_params": set | None,
      "merged_calcs":  set | None,
      "disagreed_params": list,
      "disagreed_calcs":  list,
    }
    """
    gold_a = load_gold_standard(path_a)
    gold_b = load_gold_standard(path_b)

    all_params = gold_a["params"] | gold_b["params"]
    all_calcs = gold_a["calcs"] | gold_b["calcs"]

    # 将集合转换为二值向量计算 kappa
    param_list = sorted(all_params)
    vec_a_p = [1 if p in gold_a["params"] else 0 for p in param_list]
    vec_b_p = [1 if p in gold_b["params"] else 0 for p in param_list]

    calc_list = sorted(all_calcs)
    vec_a_c = [1 if c in gold_a["calcs"] else 0 for c in calc_list]
    vec_b_c = [1 if c in gold_b["calcs"] else 0 for c in calc_list]

    combined_a = vec_a_p + vec_a_c
    combined_b = vec_b_p + vec_b_c
    kappa = cohen_kappa_binary(combined_a, combined_b)

    needs_review = kappa < threshold
    merged_params = None
    merged_calcs = None

    disagreed_params = [
        p for p, a, b in zip(param_list, vec_a_p, vec_b_p) if a != b
    ]
    disagreed_calcs = [
        c for c, a, b in zip(calc_list, vec_a_c, vec_b_c) if a != b
    ]

    if not needs_review:
        # 取交集作为保守合并（两人均标注才算金标准）
        merged_params = gold_a["params"] & gold_b["params"]
        merged_calcs = gold_a["calcs"] & gold_b["calcs"]

    return {
        "kappa": kappa,
        "needs_review": needs_review,
        "merged_params": merged_params,
        "merged_calcs": merged_calcs,
        "disagreed_params": disagreed_params,
        "disagreed_calcs": disagreed_calcs,
    }
