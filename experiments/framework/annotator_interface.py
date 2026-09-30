"""
annotator_interface.py — 读写人工标注 JSON，计算标注者间一致性。

标注文件由两名机械工程人员分别填写，存放在：
  dataset/annotations/{task_id}_{annotator_id}.json

本模块提供加载、校验、kappa 计算和分歧导出功能。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gold_standard import cohen_kappa_binary


# ---------------------------------------------------------------------------
# 参数证据标注（E3 / E12 使用）
# ---------------------------------------------------------------------------

PARAM_ANNOTATION_SCHEMA = {
    "task_id": str,
    "run_id": str,
    "annotator_id": str,
    "parameters": list,   # list of ParameterAnnotation
}

PARAMETER_ANNOTATION_KEYS = [
    "param_id",
    "has_source",           # 是否有明确来源
    "source_matches",       # 来源是否匹配参数性质
    "has_calc_or_std",      # 是否有计算或标准依据
    "has_design_reason",    # 是否有设计理由
    "traceable_to_input",   # 是否能从报告追溯到原始输入
    "consistent_version",   # 是否与当前版本一致
]


def load_annotation(path: str | Path) -> dict[str, Any]:
    """加载标注 JSON，返回原始 dict。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"标注文件不存在: {p}")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_annotation(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_empty_param_annotation(
    task_id: str, run_id: str, annotator_id: str, param_ids: list[str]
) -> dict[str, Any]:
    """
    生成空白参数标注模板，供标注者填写。
    每个布尔字段默认为 null（未填写），填写时改为 true/false。
    """
    return {
        "task_id": task_id,
        "run_id": run_id,
        "annotator_id": annotator_id,
        "parameters": [
            {
                "param_id": pid,
                "has_source": None,
                "source_matches": None,
                "has_calc_or_std": None,
                "has_design_reason": None,
                "traceable_to_input": None,
                "consistent_version": None,
                "notes": "",
            }
            for pid in param_ids
        ],
    }


def compute_inter_rater_kappa(
    annotation_a: dict[str, Any],
    annotation_b: dict[str, Any],
    keys: list[str] | None = None,
) -> dict[str, float]:
    """
    计算两名标注者在所有参数 × 所有二值字段上的 Cohen's kappa。

    返回 {field: kappa, ..., "overall": kappa}
    keys 为空时使用 PARAMETER_ANNOTATION_KEYS 中除 param_id 以外的字段。
    """
    if keys is None:
        keys = [k for k in PARAMETER_ANNOTATION_KEYS if k != "param_id"]

    # 按 param_id 对齐
    params_a = {p["param_id"]: p for p in annotation_a.get("parameters", [])}
    params_b = {p["param_id"]: p for p in annotation_b.get("parameters", [])}
    common_ids = sorted(set(params_a.keys()) & set(params_b.keys()))

    if not common_ids:
        return {"overall": 0.0}

    results: dict[str, float] = {}
    all_a: list[int] = []
    all_b: list[int] = []

    for key in keys:
        vec_a = []
        vec_b = []
        for pid in common_ids:
            val_a = params_a[pid].get(key)
            val_b = params_b[pid].get(key)
            if val_a is None or val_b is None:
                continue   # 跳过未填写项
            vec_a.append(1 if val_a else 0)
            vec_b.append(1 if val_b else 0)
        if vec_a:
            results[key] = cohen_kappa_binary(vec_a, vec_b)
            all_a.extend(vec_a)
            all_b.extend(vec_b)

    results["overall"] = cohen_kappa_binary(all_a, all_b) if all_a else 0.0
    return results


def find_disagreements(
    annotation_a: dict[str, Any],
    annotation_b: dict[str, Any],
    keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    列出两名标注者在各字段上的具体分歧项，供第三名裁决者使用。
    """
    if keys is None:
        keys = [k for k in PARAMETER_ANNOTATION_KEYS if k != "param_id"]

    params_a = {p["param_id"]: p for p in annotation_a.get("parameters", [])}
    params_b = {p["param_id"]: p for p in annotation_b.get("parameters", [])}
    common_ids = sorted(set(params_a.keys()) & set(params_b.keys()))

    disagreements = []
    for pid in common_ids:
        pa = params_a[pid]
        pb = params_b[pid]
        for key in keys:
            va = pa.get(key)
            vb = pb.get(key)
            if va is None or vb is None:
                continue
            if bool(va) != bool(vb):
                disagreements.append({
                    "param_id": pid,
                    "field": key,
                    "annotator_a": va,
                    "annotator_b": vb,
                    "annotator_a_id": annotation_a.get("annotator_id", "A"),
                    "annotator_b_id": annotation_b.get("annotator_id", "B"),
                })
    return disagreements
