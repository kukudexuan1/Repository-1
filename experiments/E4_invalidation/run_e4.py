"""E4 deterministic invalidation-propagation experiment runner."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.metrics.propagation import compute_propagation_metrics
from framework.run_manager import RunContext, load_config

console = Console()
EXPERIMENT_ID = "E4"
ROOT = Path(__file__).parent
MANIFEST_PATH = ROOT / "change_scenarios.json"
GOLD_PATH = ROOT / "gold_annotations.json"
E4_CONDITIONS = {
    "C1_no_graph": "none",
    "C2_full_invalidation": "full",
    "C3_direct_only": "direct",
    "P_recursive": "recursive",
}


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _request(method: str, base_url: str, path: str, timeout: float, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = httpx.request(method, f"{base_url.rstrip('/')}{path}", json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def load_manifest() -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    manifest = _read_json(MANIFEST_PATH)
    baselines = manifest.get("baselines", []) if isinstance(manifest, dict) else []
    if not isinstance(baselines, list) or not baselines:
        raise ValueError("change_scenarios.json 必须包含非空 baselines")
    raw_gold = _read_json(GOLD_PATH)
    annotations = raw_gold.get("annotations", []) if isinstance(raw_gold, dict) else []
    gold = {(str(item.get("sample_id")), str(item.get("change_id"))): item for item in annotations}
    return baselines, gold


def validate_manifest(
    baselines: list[dict[str, Any]],
    gold: dict[tuple[str, str], dict[str, Any]],
    *,
    require_adjudication: bool = True,
) -> None:
    seen_samples: set[str] = set()
    for baseline in baselines:
        sample_id = str(baseline.get("sample_id", "")).strip()
        session_id = str(baseline.get("session_id", "")).strip()
        changes = baseline.get("changes", [])
        if not sample_id or sample_id in seen_samples:
            raise ValueError(f"sample_id 缺失或重复: {sample_id!r}")
        seen_samples.add(sample_id)
        if not session_id or session_id.startswith("REPLACE_"):
            raise ValueError(f"{sample_id} 尚未填写人工 baseline session_id")
        if not isinstance(changes, list) or len(changes) < 5:
            raise ValueError(f"{sample_id} 必须包含至少 5 个变化")
        seen_changes: set[str] = set()
        for change in changes:
            change_id = str(change.get("change_id", "")).strip()
            if not change_id or change_id in seen_changes:
                raise ValueError(f"{sample_id} change_id 缺失或重复: {change_id!r}")
            seen_changes.add(change_id)
            if not isinstance(change.get("new_value"), (int, float)) or isinstance(change.get("new_value"), bool):
                raise ValueError(f"{sample_id}/{change_id} 不是数值 Quantity 变化")
            annotation = gold.get((sample_id, change_id))
            if annotation is None:
                raise ValueError(f"缺少 {sample_id}/{change_id} 的独立专家 gold")
            if require_adjudication and not annotation.get("adjudicated", False):
                raise ValueError(f"{sample_id}/{change_id} 的 gold 尚未裁决")
            if require_adjudication and float(annotation.get("kappa", 0)) < 0.8:
                raise ValueError(f"{sample_id}/{change_id} 的 kappa 低于 0.8")
            if require_adjudication:
                annotator_b = annotation.get("annotator_b", {})
                if annotator_b.get("identity") == "REQUIRED_INDEPENDENT_HUMAN_EXPERT":
                    raise ValueError(f"{sample_id}/{change_id} 尚缺第二位独立专家标注")
            for key in ("gold_stale_params", "gold_stale_calcs"):
                if not isinstance(annotation.get(key), list):
                    raise ValueError(f"{sample_id}/{change_id} 的 {key} 必须是列表")
            if not annotation["gold_stale_params"] and not annotation["gold_stale_calcs"]:
                raise ValueError(f"{sample_id}/{change_id} 的 gold 受影响集合不能为空")


def validate_baseline_state(baseline: dict[str, Any], sample: dict[str, Any]) -> None:
    entries = baseline.get("ledger", {}).get("entries", {})
    calcs = baseline.get("calculations", {})
    if not entries or not calcs:
        raise ValueError(f"{sample['sample_id']} baseline 必须同时包含台账和计算记录")
    if any(entry.get("status") == "stale" for entry in entries.values()) or any(record.get("stale") for record in calcs.values()):
        raise ValueError(f"{sample['sample_id']} baseline 不能包含 stale 项")
    for change in sample["changes"]:
        symbol = change["changed_param"]
        entry = entries.get(symbol)
        if entry is None:
            raise ValueError(f"baseline 缺少变化参数 {symbol}")
        actual = entry.get("value", {}).get("value")
        if actual != change["old_value"]:
            raise ValueError(f"{symbol} baseline={actual}，manifest old_value={change['old_value']}")


def _cohen_kappa(marked_a: set[str], marked_b: set[str], universe: set[str]) -> float:
    if not universe:
        raise ValueError("无法在空节点集合上计算 Cohen's kappa")
    a = marked_a & universe
    b = marked_b & universe
    observed = (len(a & b) + len((universe - a) & (universe - b))) / len(universe)
    p_a = len(a) / len(universe)
    p_b = len(b) / len(universe)
    expected = p_a * p_b + (1 - p_a) * (1 - p_b)
    if expected == 1:
        return 1.0
    return round((observed - expected) / (1 - expected), 4)


def validate_annotation_agreement(
    annotation: dict[str, Any],
    entries: dict[str, Any],
    calcs: dict[str, Any],
) -> float:
    universe = set(entries) | set(calcs)
    annotator_a = annotation.get("annotator_a", {})
    annotator_b = annotation.get("annotator_b", {})
    marked_a = set(annotator_a.get("stale_params", [])) | set(annotator_a.get("stale_calcs", []))
    marked_b = set(annotator_b.get("stale_params", [])) | set(annotator_b.get("stale_calcs", []))
    unknown = (marked_a | marked_b) - universe
    if unknown:
        raise ValueError(f"专家标注引用了 baseline 不存在节点: {sorted(unknown)}")
    kappa = _cohen_kappa(marked_a, marked_b, universe)
    declared = round(float(annotation.get("kappa", 0)), 4)
    if declared < 0.8:
        raise ValueError(f"标注声明 Cohen's kappa={declared}，低于 0.8")
    final_gold = set(annotation["gold_stale_params"]) | set(annotation["gold_stale_calcs"])
    if final_gold - (marked_a | marked_b):
        raise ValueError("裁决 gold 包含两位专家均未标注的节点")
    return kappa


def _stale_sets(state: dict[str, Any]) -> tuple[set[str], set[str]]:
    entries = state.get("ledger", {}).get("entries", {})
    calcs = state.get("calculations", {})
    return (
        {symbol for symbol, entry in entries.items() if entry.get("status") == "stale"},
        {record_id for record_id, record in calcs.items() if record.get("stale")},
    )


def _probe_leakage(probe: dict[str, Any]) -> tuple[int, int, list[str]]:
    accepted_params = [item["symbol"] for item in probe.get("entries", []) if item.get("accepted")]
    report_accepted = bool(probe.get("report", {}).get("accepted"))
    accepted_calcs = [item["record_id"] for item in probe.get("records", [])] if report_accepted else []
    return len(accepted_params), len(accepted_calcs), [*accepted_params, *accepted_calcs]


def run_case(base_url: str, timeout: float, timeout_recovery: float, baseline: dict[str, Any], change: dict[str, Any], annotation: dict[str, Any], condition: str, mode: str, replicate: int, cfg: dict[str, Any]) -> dict[str, Any]:
    sample_id = baseline["sample_id"]
    case_id = f"{sample_id}_{change['change_id']}"
    ctx = RunContext.create(EXPERIMENT_ID, case_id, condition, replicate, cfg)
    stage = "baseline"
    events: list[dict[str, Any]] = []
    try:
        state_before = _request("GET", base_url, f"/api/sessions/{baseline['session_id']}", timeout)
        validate_baseline_state(state_before, baseline)
        clone = _request("POST", base_url, f"/api/sessions/{baseline['session_id']}/clone", timeout, {})
        session_id = clone["session_id"]
        stage = "change"
        changed_at = time.perf_counter()
        change_response = _request("POST", base_url, "/api/experiments/e4/change", timeout, {
            "session_id": session_id,
            "symbol": change["changed_param"],
            "value": change["new_value"],
            "unit": change.get("unit", ""),
            "propagation_mode": mode,
        })
        change_elapsed = time.perf_counter() - changed_at
        state_after = _request("GET", base_url, f"/api/sessions/{session_id}", timeout)
        predicted_params, predicted_calcs = _stale_sets(state_after)
        gold_params = set(annotation["gold_stale_params"])
        gold_calcs = set(annotation["gold_stale_calcs"])
        stage = "downstream_probe"
        probed_at = time.perf_counter()
        probe = _request("POST", base_url, "/api/experiments/e4/probe", timeout, {
            "session_id": session_id,
            "symbols": sorted(gold_params),
            "record_ids": sorted(gold_calcs),
        })
        probe_elapsed = time.perf_counter() - probed_at
        leaked_params, leaked_calcs, leaked_nodes = _probe_leakage(probe)
        predicted = predicted_params | predicted_calcs
        full_nodes = len(state_before.get("ledger", {}).get("entries", {})) + len(state_before.get("calculations", {}))
        stage = "recovery"
        recovery_started = time.perf_counter()
        stale_after = predicted_params | predicted_calcs
        if mode == "none" or not stale_after:
            recovery_response: dict[str, Any] = {"tool_calls_made": [], "tool_events": [], "_skipped": True}
            recovery_elapsed = 0.0
            recovered_state = state_after
        else:
            recovery_response = _request(
                "POST", base_url, "/api/workflow/run", timeout_recovery,
                {"session_id": session_id, "user_prompt": "执行受控恢复：查询台账和计算记录，只重算当前输入变化影响的计算与参数；不得使用 stale 数据，不得建模、价真、生成报告或发起用户决策；完成后立即停止。"},
                {"X-Experiment-Condition": "B3", "X-Propagation-Mode": mode, "X-Max-Agent-Iterations": "12"},
            )
            recovery_elapsed = time.perf_counter() - recovery_started
            recovered_state = _request("GET", base_url, f"/api/sessions/{session_id}", timeout)
        recovered_params, recovered_calcs = _stale_sets(recovered_state)
        before_calc_ids = set(state_after.get("calculations", {}))
        after_calc_ids = set(recovered_state.get("calculations", {}))
        actual_recalculations = sum(
            1
            for event in recovery_response.get("tool_events", [])
            if event.get("name") in {"solve_formula", "run_calculation"}
            and event.get("status") == "ok"
        )
        new_calculation_records = len(after_calc_ids - before_calc_ids)
        recovery_tool_calls = list(recovery_response.get("tool_calls_made", []))
        run_data = {
            "predicted_stale_params": sorted(predicted_params),
            "predicted_stale_calcs": sorted(predicted_calcs),
            "gold_stale_params": sorted(gold_params),
            "gold_stale_calcs": sorted(gold_calcs),
            "stale_params_used_downstream": leaked_params,
            "stale_calcs_used_downstream": leaked_calcs,
            "n_incremental_recalculations": actual_recalculations,
            "n_full_recalculations": full_nodes,
            "recovery_time_s": round(recovery_elapsed, 4),
            "tool_calls_after_change": len(recovery_tool_calls) + 2,
            "human_interventions": 0,
            "change_time_s": round(change_elapsed, 4),
            "probe_time_s": round(probe_elapsed, 4),
            "leaked_nodes": leaked_nodes,
            "condition_semantics": "C2 marks every existing node stale before bounded recovery",
            "recovered_stale_params": sorted(recovered_params),
            "recovered_stale_calcs": sorted(recovered_calcs),
            "actual_recalculations": actual_recalculations,
            "new_calculation_records": new_calculation_records,
            "recovery_tool_calls": recovery_tool_calls,
        }
        metrics = compute_propagation_metrics(run_data)
        events.extend([
            {"stage": "change", "kind": "deterministic_backend_operation", "elapsed_s": round(change_elapsed, 4)},
            {"stage": "downstream_probe", "kind": "geometry_and_report_gate_probe", "elapsed_s": round(probe_elapsed, 4)},
            {"stage": "recovery", "kind": "bounded_agent_workflow", "elapsed_s": round(recovery_elapsed, 4), "tool_calls": recovery_tool_calls},
        ])
        ctx.write("input.json", {"sample_id": sample_id, "task_id": baseline["task_id"], "change": change, "condition": condition, "mode": mode, "baseline_session_id": baseline["session_id"], "clone_session_id": session_id, "replicate": replicate})
        ctx.write("state_before.json", state_before)
        ctx.write("state_after_invalidation.json", state_after)
        ctx.write("state_after.json", recovered_state)
        ctx.write("gold_dependency_closure.json", annotation)
        ctx.write("model_outputs.json", {"metrics": metrics, "run_data": run_data, "probe": probe, "change_response": change_response, "recovery_response": recovery_response})
        ctx.write("calculation_records.json", recovered_state.get("calculations", {}))
        ctx.write("ledger_snapshot.json", recovered_state.get("ledger", {}))
        ctx.write("tool_trace.json", events)
        ctx.finalize(success=True)
        return {"case_id": case_id, "condition": condition, **metrics}
    except Exception as exc:  # noqa: BLE001
        ctx.append_stderr(f"stage={stage} {type(exc).__name__}: {exc}")
        ctx.log_exception()
        events.append({"stage": stage, "error_type": type(exc).__name__, "error": str(exc)})
        ctx.write("tool_trace.json", events)
        ctx.finalize(success=False)
        return {"case_id": case_id, "condition": condition, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run protocol-compliant E4 invalidation experiment")
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--condition", choices=[*E4_CONDITIONS, "all"], default="all")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--validate-draft",
        action="store_true",
        help="校验 baseline 与候选 gold 结构，不绕过正式实验的独立裁决要求",
    )
    args = parser.parse_args()
    if args.replicates < 5:
        raise SystemExit("E4 协议要求至少 5 次独立重复")
    baselines, gold = load_manifest()
    validate_manifest(baselines, gold, require_adjudication=not args.validate_draft)
    cfg = load_config()
    base_url = str(cfg["backend"]["url"])
    timeout = float(cfg["backend"].get("timeout_read", 300))
    timeout_recovery = float(cfg["backend"].get("timeout_recovery", 600))
    for baseline in baselines:
        state = _request("GET", base_url, f"/api/sessions/{baseline['session_id']}", timeout)
        validate_baseline_state(state, baseline)
        entries = state.get("ledger", {}).get("entries", {})
        calcs = state.get("calculations", {})
        for change in baseline["changes"]:
            annotation = gold[(baseline["sample_id"], change["change_id"])]
            missing_params = set(annotation["gold_stale_params"]) - set(entries)
            missing_calcs = set(annotation["gold_stale_calcs"]) - set(calcs)
            if missing_params or missing_calcs:
                raise ValueError(
                    f"{baseline['sample_id']}/{change['change_id']} gold 引用了不存在节点: "
                    f"params={sorted(missing_params)}, calcs={sorted(missing_calcs)}"
                )
            if not args.validate_draft:
                validate_annotation_agreement(annotation, entries, calcs)
    if args.validate_draft:
        console.print(
            f"E4 draft validation passed: baselines={len(baselines)}, "
            f"changes={sum(len(item['changes']) for item in baselines)}; "
            "formal run remains blocked until independent adjudication"
        )
        return
    if args.validate_only:
        console.print(f"E4 validation passed: baselines={len(baselines)}, changes={sum(len(item['changes']) for item in baselines)}")
        return
    conditions = E4_CONDITIONS if args.condition == "all" else {args.condition: E4_CONDITIONS[args.condition]}
    results: dict[str, list[dict[str, Any]]] = {name: [] for name in conditions}
    for replicate in range(1, args.replicates + 1):
        for condition, mode in conditions.items():
            for baseline in baselines:
                for change in baseline["changes"]:
                    annotation = gold[(baseline["sample_id"], change["change_id"])]
                    result = run_case(base_url, timeout, timeout_recovery, baseline, change, annotation, condition, mode, replicate, cfg)
                    results[condition].append(result)
                    console.print(f"rep={replicate} {result['case_id']} [{condition}] {result.get('IR', 'failed')} {result.get('error', '')}")
    table = Table(title="E4 deterministic summary")
    for column in ("condition", "valid", "failed", "IR", "ORR", "BR", "IRE"):
        table.add_column(column)
    for condition, rows in results.items():
        valid = [row for row in rows if "IR" in row]
        failed = len(rows) - len(valid)
        values = [f"{sum(row[key] for row in valid) / len(valid):.3f}" for key in ("IR", "ORR", "BR", "IRE")] if valid else ["N/A"] * 4
        table.add_row(condition, str(len(valid)), str(failed), *values)
    console.print(table)


if __name__ == "__main__":
    main()
