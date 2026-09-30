"""
run_e2.py - E2 unit and formula constraint experiment.

Each case is executed in a fresh backend session. Classification uses structured
agent tool events first and falls back to conservative model-judgment patterns.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from framework.backend_client import BackendClient
from framework.condition import Condition
from framework.metrics.stats import fisher_exact
from framework.progress import progress
from framework.run_manager import RunContext, load_config

console = Console()
EXPERIMENT_ID = "E2"
CASES_PATH = Path(__file__).parent / "error_cases.json"
CONDITIONS = [Condition.B0, Condition.B1, Condition.B2, Condition.P]
_REQUIRED_CASE_FIELDS = {"case_id", "error_type", "prompt"}


def load_cases() -> list[dict]:
    if not CASES_PATH.exists():
        raise FileNotFoundError(f"错误案例文件不存在: {CASES_PATH}")
    with CASES_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    cases = [item for item in raw if isinstance(item, dict) and "case_id" in item]
    invalid = [item for item in cases if not _REQUIRED_CASE_FIELDS.issubset(item)]
    if invalid:
        ids = [item.get("case_id", "<unknown>") for item in invalid]
        raise ValueError(f"E2 案例缺少必需字段: {ids}")
    if not cases:
        raise ValueError("E2 案例集为空")
    return cases


def _model_rejection(reply: str) -> bool:
    text = reply.lower()
    patterns = (
        r"无法继续",
        r"不能计算",
        r"不能直接计算",
        r"无法确定",
        r"无法判断",
        r"不应继续",
        r"不可接受",
        r"输入.*(?:错误|无效)",
        r"(?:错误|无效).*输入",
        r"拒绝(?:计算|执行|接受)",
        r"cannot (?:calculate|proceed|accept)",
        r"invalid input",
        r"rejected",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _classify_response(result: dict, case: dict) -> dict:
    response = result.get("response", {})
    reply = response.get("reply", "")
    events = response.get("tool_events", [])
    if not events:
        events = [event for trace in result.get("tool_trace", []) for event in trace.get("tool_events", [])]

    refused = [event for event in events if event.get("status") == "refused"]
    tool_errors = [event for event in events if event.get("status") in {"error", "exception"}]
    successful_tools = [event for event in events if event.get("status") == "ok"]
    model_rejected = _model_rejection(reply)

    if refused:
        outcome = "rejected"
        reject_source = "structured_tool_refusal"
    elif tool_errors:
        outcome = "failed"
        reject_source = "tool_error"
    elif model_rejected:
        outcome = "rejected"
        reject_source = "model_judgment"
    elif successful_tools:
        outcome = "accepted"
        reject_source = "none"
    else:
        outcome = "accepted"
        reject_source = "none"

    return {
        "case_id": case["case_id"],
        "error_type": case["error_type"],
        "is_error_input": case.get("is_error_input", True),
        "outcome": outcome,
        "was_rejected": outcome == "rejected",
        "was_accepted": outcome == "accepted",
        "reject_source": reject_source,
        "tool_calls_made": response.get("tool_calls_made", []),
        "tool_events": events,
        "reply_snippet": reply[:500],
    }


def compute_e2_metrics(classified: list[dict]) -> dict:
    error_cases = [case for case in classified if case["is_error_input"]]
    normal_cases = [case for case in classified if not case["is_error_input"]]
    completed_cases = [case for case in classified if case["outcome"] != "failed"]
    detected = [case for case in error_cases if case["was_rejected"]]
    accepted_errors = [case for case in error_cases if case["was_accepted"]]
    blocked_normal = [case for case in normal_cases if case["was_rejected"]]
    passed_normal = [case for case in normal_cases if case["was_accepted"]]

    by_type: dict[str, dict] = {}
    for case in error_cases:
        item = by_type.setdefault(case["error_type"], {"n": 0, "detected": 0, "accepted": 0, "failed": 0})
        item["n"] += 1
        item["detected"] += int(case["was_rejected"])
        item["accepted"] += int(case["was_accepted"])
        item["failed"] += int(case["outcome"] == "failed")
    for item in by_type.values():
        item["detection_rate"] = round(item["detected"] / item["n"], 4) if item["n"] else 0.0

    reject_sources = Counter(case["reject_source"] for case in classified if case["was_rejected"])
    n_error = len(error_cases)
    n_normal = len(normal_cases)
    return {
        "n_cases": len(classified),
        "n_error_cases": n_error,
        "n_normal_cases": n_normal,
        "n_completed_cases": len(completed_cases),
        "n_failed_cases": len(classified) - len(completed_cases),
        "n_detected_errors": len(detected),
        "n_accepted_errors": len(accepted_errors),
        "n_blocked_normal": len(blocked_normal),
        "n_passed_normal": len(passed_normal),
        "error_detection_rate": round(len(detected) / n_error, 4) if n_error else 0.0,
        "correct_rejection_rate": round(len(detected) / n_error, 4) if n_error else 0.0,
        "unsafe_acceptance_rate": round(len(accepted_errors) / n_error, 4) if n_error else 0.0,
        "false_acceptance_rate": round(len(accepted_errors) / n_error, 4) if n_error else 0.0,
        "false_rejection_rate": round(len(blocked_normal) / n_normal, 4) if n_normal else 0.0,
        "normal_pass_rate": round(len(passed_normal) / n_normal, 4) if n_normal else 0.0,
        "normal_block_rate": round(len(blocked_normal) / n_normal, 4) if n_normal else 0.0,
        "by_error_type": by_type,
        "reject_sources": dict(reject_sources),
    }


def run_condition(condition: Condition, cases: list[dict], cfg: dict, replicate: int = 1) -> dict:
    classified: list[dict] = []
    traces: list[dict] = []
    failures: list[dict] = []

    for case in cases:
        ctx = RunContext.create(EXPERIMENT_ID, case["case_id"], condition.value, replicate=replicate, base_cfg=cfg)
        client = BackendClient(condition)
        ctx.write("input.json", {"condition": condition.value, "case": case})
        try:
            result = client.run(case["prompt"], capture_state=True)
            result["tool_trace"] = client.get_tool_trace()
            item = _classify_response(result, case)
            traces.extend(client.get_tool_trace())
            ctx.write("state_before.json", result.get("state_before", {}))
            ctx.write("state_after.json", result.get("state_after", {}))
            ctx.write("tool_trace.json", client.get_tool_trace())
            ctx.write("model_outputs.json", item)
            ctx.write("calculation_records.json", result.get("state_after", {}).get("calculation_records", []))
            ctx.write("ledger_snapshot.json", result.get("state_after", {}).get("parameter_ledger", {}))
            classified.append(item)
            ctx.finalize(success=True)
        except Exception as exc:  # noqa: BLE001
            failure = {"case_id": case["case_id"], "error_type": case["error_type"], "is_error_input": case.get("is_error_input", True), "outcome": "failed", "was_rejected": False, "was_accepted": False, "reject_source": "runner_exception", "error": str(exc)}
            failures.append(failure)
            classified.append(failure)
            ctx.append_stderr(str(exc))
            ctx.write("tool_trace.json", client.get_tool_trace())
            ctx.write("model_outputs.json", failure)
            ctx.finalize(success=False)

    metrics = compute_e2_metrics(classified)
    metrics["failures"] = failures
    return metrics


def main() -> None:
    cfg = load_config()
    cases = load_cases()
    counts = Counter(case["error_type"] for case in cases)
    n_normal = sum(not case.get("is_error_input", True) for case in cases)
    console.print(f"\n[bold]E2 单位与公式约束实验[/bold]  n_cases={len(cases)}  n_normal={n_normal}  distribution={dict(counts)}")

    all_metrics: dict[str, dict] = {}
    for condition in progress(CONDITIONS, total=len(CONDITIONS), description="E2条件", unit="condition"):
        metrics = run_condition(condition, cases, cfg)
        all_metrics[condition.value] = metrics
        console.print(f"  {condition.value}: DR={metrics['error_detection_rate']:.1%} FPR={metrics['false_rejection_rate']:.1%} failures={metrics['n_failed_cases']}")

    b0 = all_metrics.get("B0")
    p = all_metrics.get("P")
    if b0 and p:
        stat = fisher_exact(b0["n_detected_errors"], b0["n_error_cases"], p["n_detected_errors"], p["n_error_cases"])
        console.print(f"\nFisher exact (B0 vs P 正确拒绝率): OR={stat['odds_ratio']:.3f} p={stat['p_value']:.4f}")

    table = Table(title="E2 实验汇总", show_header=True)
    for column in ("条件", "错误识别率", "误拒率", "正常放行率", "失败数"):
        table.add_column(column)
    for name, metrics in all_metrics.items():
        table.add_row(name, f"{metrics['error_detection_rate']:.1%}", f"{metrics['false_rejection_rate']:.1%}", f"{metrics['normal_pass_rate']:.1%}", str(metrics["n_failed_cases"]))
    console.print(table)


if __name__ == "__main__":
    main()
