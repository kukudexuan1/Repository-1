"""
retrieval.py — E1 知识检索准确性指标。

实现协议 §E1 的 Precision@k, Recall@k, MRR 和禁用结果暴露率。
所有函数接受纯 Python 列表，不依赖任何 backend 内部对象。
"""

from __future__ import annotations

from typing import Any


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """P@k = 前k个结果中相关结果数 / k"""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return round(hits / k, 4)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """R@k = 前k个结果中相关结果数 / 标注相关结果总数"""
    if not relevant:
        return 1.0
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return round(hits / len(relevant), 4)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """首个正确结果排名的倒数，找不到则为 0。"""
    for i, r in enumerate(retrieved, start=1):
        if r in relevant:
            return round(1.0 / i, 4)
    return 0.0


def mean_reciprocal_rank(queries: list[dict[str, Any]]) -> float:
    """
    MRR：所有查询的 reciprocal rank 均值。

    queries 格式：
    [{"retrieved": [...], "relevant": [...或set]}, ...]
    """
    if not queries:
        return 0.0
    rr_sum = 0.0
    for q in queries:
        retrieved = q.get("retrieved", [])
        relevant = set(q.get("relevant", []))
        rr_sum += reciprocal_rank(retrieved, relevant)
    return round(rr_sum / len(queries), 4)


def forbidden_exposure_rate(
    retrieved: list[str], forbidden: set[str], k: int | None = None
) -> float:
    """
    禁用结果暴露率：不适用公式、过期标准或错误材料出现在推荐结果中的比例。

    k=None 时检查全部返回结果。
    """
    pool = retrieved[:k] if k is not None else retrieved
    if not pool:
        return 0.0
    hits = sum(1 for r in pool if r in forbidden)
    return round(hits / len(pool), 4)


def compute_retrieval_metrics(
    queries: list[dict[str, Any]], ks: list[int] | None = None
) -> dict[str, Any]:
    """
    批量计算所有查询的检索指标。

    queries 格式：
    [
      {
        "query_id": "q001",
        "retrieved": ["id1", "id2", ...],
        "relevant": ["id1", "id3"],
        "forbidden": ["id_bad1"],  # 可选
      },
      ...
    ]

    返回：
    {
      "mrr": float,
      "p@1": float, "p@3": float, "p@5": float,
      "r@1": float, "r@3": float, "r@5": float,
      "forbidden_exposure_rate": float,
      "per_query": [...]
    }
    """
    if ks is None:
        ks = [1, 3, 5]

    per_query = []
    forbidden_hits = 0
    forbidden_total = 0

    for q in queries:
        qid = q.get("query_id", "")
        retrieved = q.get("retrieved", [])
        relevant = set(q.get("relevant", []))
        forbidden = set(q.get("forbidden", []))

        entry: dict[str, Any] = {"query_id": qid, "rr": reciprocal_rank(retrieved, relevant)}
        for k in ks:
            entry[f"p@{k}"] = precision_at_k(retrieved, relevant, k)
            entry[f"r@{k}"] = recall_at_k(retrieved, relevant, k)

        if forbidden:
            fer = forbidden_exposure_rate(retrieved, forbidden)
            entry["forbidden_exposure_rate"] = fer
            forbidden_hits += sum(1 for r in retrieved if r in forbidden)
            forbidden_total += len(retrieved)

        per_query.append(entry)

    n = len(queries)
    result: dict[str, Any] = {
        "n_queries": n,
        "mrr": round(sum(e["rr"] for e in per_query) / n, 4) if n else 0.0,
    }
    for k in ks:
        result[f"p@{k}"] = round(sum(e[f"p@{k}"] for e in per_query) / n, 4) if n else 0.0
        result[f"r@{k}"] = round(sum(e[f"r@{k}"] for e in per_query) / n, 4) if n else 0.0

    result["forbidden_exposure_rate"] = (
        round(forbidden_hits / forbidden_total, 4) if forbidden_total else 0.0
    )
    result["per_query"] = per_query
    return result
