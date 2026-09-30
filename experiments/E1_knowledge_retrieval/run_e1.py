"""
run_e1.py — E1 机械知识检索准确性实验。

协议 §E1：80 个专家标注查询（公式30+材料15+标准系列15+标准件20），
分别测试关键词/带类别/精确ID/普通RAG四种检索策略，
计算 P@k, R@k, MRR, 禁用结果暴露率。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from framework.backend_client import BackendClient
from framework.condition import Condition
from framework.metrics.retrieval import compute_retrieval_metrics
from framework.metrics.stats import bootstrap_ci, wilcoxon_signed_rank
from framework.progress import progress
from framework.run_manager import RunContext, load_config

console = Console()
EXPERIMENT_ID = "E1"
QUERIES_PATH = Path(__file__).parent / "queries.json"


def load_queries() -> list[dict]:
    if not QUERIES_PATH.exists():
        raise FileNotFoundError(
            f"查询文件不存在: {QUERIES_PATH}\n"
            "请先填写 E1_knowledge_retrieval/queries.json（共80个专家标注查询）"
        )
    with QUERIES_PATH.open(encoding="utf-8-sig") as f:
        queries = json.load(f)
    if len(queries) != 80:
        raise ValueError(f"E1 查询数量必须为80，当前为{len(queries)}")
    return queries


def _call_retrieval(
    client: BackendClient,
    query: dict,
    strategy: str,
    ctx: RunContext,
) -> list[str]:
    """调用 backend 结构化知识检索接口，返回真实知识库 ID。"""
    search_text = (
        query.get("known_id", query["query_text"])
        if strategy == "exact_id"
        else query["query_text"]
    )
    category = query.get("category", "") if strategy != "rag" else ""

    try:
        result = client.search_knowledge(
            query=search_text,
            category=category,
            strategy=strategy,
            limit=5,
        )
        return [str(item) for item in result.get("result_ids", [])]
    except Exception as exc:  # noqa: BLE001
        ctx.append_stderr(f"E1 retrieval error ({strategy}, {query['query_id']}): {exc}")
        return []


def run_e1(condition: Condition = Condition.B1) -> None:
    cfg = load_config()
    queries = load_queries()
    ctx = RunContext.create(EXPERIMENT_ID, "all_queries", condition.value, replicate=1, base_cfg=cfg)
    console.print(f"\n[bold]E1 实验开始[/bold]  condition={condition.value}  n_queries={len(queries)}")

    client = BackendClient(condition)
    strategies = ["keyword", "category", "exact_id", "rag"]
    all_strategy_results: dict[str, dict] = {}

    for strategy in strategies:
        console.print(f"  策略: [cyan]{strategy}[/cyan]")
        enriched: list[dict] = []
        for q in progress(queries, total=len(queries), description=strategy, unit="query"):
            retrieved = _call_retrieval(client, q, strategy, ctx)
            enriched.append({
                "query_id": q["query_id"],
                "retrieved": retrieved,
                "relevant": q.get("relevant", []),
                "forbidden": q.get("forbidden", []),
            })
        metrics = compute_retrieval_metrics(enriched, ks=[1, 3, 5])
        all_strategy_results[strategy] = metrics
        console.print(
            f"    MRR={metrics['mrr']:.3f}  P@1={metrics['p@1']:.3f}  "
            f"R@5={metrics['r@5']:.3f}  Forbidden={metrics['forbidden_exposure_rate']:.3f}"
        )

    kw_rrs = [e["rr"] for e in all_strategy_results["keyword"].get("per_query", [])]
    rag_rrs = [e["rr"] for e in all_strategy_results["rag"].get("per_query", [])]
    stat_kw_rag: dict = {}
    if len(kw_rrs) == len(rag_rrs) and kw_rrs:
        stat_kw_rag = wilcoxon_signed_rank(kw_rrs, rag_rrs)

    output = {
        "condition": condition.value,
        "strategy_metrics": all_strategy_results,
        "wilcoxon_keyword_vs_rag": stat_kw_rag,
        "mrr_ci_keyword": bootstrap_ci(kw_rrs) if kw_rrs else (0.0, 0.0),
    }
    ctx.write("model_outputs.json", output)
    ctx.write("input.json", {"queries_count": len(queries), "condition": condition.value})
    ctx.finalize(success=True)

    table = Table(title="E1 检索指标汇总", show_header=True)
    table.add_column("策略", style="cyan")
    table.add_column("MRR")
    table.add_column("P@1")
    table.add_column("P@3")
    table.add_column("R@5")
    table.add_column("禁用暴露率")
    for strategy, metrics in all_strategy_results.items():
        table.add_row(
            strategy,
            f"{metrics['mrr']:.3f}",
            f"{metrics['p@1']:.3f}",
            f"{metrics['p@3']:.3f}",
            f"{metrics['r@5']:.3f}",
            f"{metrics['forbidden_exposure_rate']:.3f}",
        )
    console.print(table)
    console.print(f"结果目录: {ctx.run_dir}")


def main() -> None:
    for condition in [Condition.B1, Condition.P]:
        run_e1(condition)


if __name__ == "__main__":
    main()
