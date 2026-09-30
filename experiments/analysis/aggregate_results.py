"""Aggregate experiment results while preserving experiment-specific units."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ImportError:
    print("缺少 pandas，请运行: pip install pandas")
    sys.exit(1)

RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results"
OUTPUT_DIR = Path(__file__).resolve().parent

METRIC_ALLOWLIST = {
    "E1": {"out.strategy_metrics.keyword.mrr", "out.strategy_metrics.keyword.p@1", "out.strategy_metrics.rag.mrr", "out.strategy_metrics.rag.p@1"},
    "E2": {"out.was_rejected", "out.was_accepted", "out.is_error_input"},
    "E3": {"out.system_metrics.system_evidence_coverage", "out.system_metrics.system_basis_coverage", "out.system_metrics.system_tcr"},
    "E4": {"out.metrics.IR", "out.metrics.invalidation_precision", "out.metrics.ORR", "out.metrics.BR", "out.metrics.IRE", "out.metrics.stale_used_downstream", "out.metrics.recovery_time_s", "out.metrics.tool_calls_after_change", "out.metrics.human_interventions"},
    "E5": {"out.record.was_blocked", "out.record.has_remediation", "out.record.caused_downstream_error", "out.record.protected_state_changed", "out.record.requires_human_review", "out.record.is_bypass_attempt", "out.record.system_blocked", "out.record.behavior_blocked", "out.record.true_bypass", "out.record.total_blocked"},
}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix.rstrip("."): value}
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}{key}" if prefix else str(key)
        if isinstance(item, dict):
            result.update(_flatten(item, f"{name}."))
        elif isinstance(item, list):
            result[name] = json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:1000]
        else:
            result[name] = item
    return result


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _unit_from_row(row: dict[str, Any]) -> str:
    experiment = str(row.get("meta.experiment_id", ""))
    if experiment == "E5":
        return str(row.get("out.record.scenario_id") or row.get("meta.case_id") or "")
    return str(row.get("out.case_id") or row.get("meta.case_id") or "")


def collect_runs(experiment_ids: list[str] | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not RESULTS_ROOT.exists():
        return pd.DataFrame()
    for exp_dir in sorted(RESULTS_ROOT.iterdir()):
        if not exp_dir.is_dir() or (experiment_ids and exp_dir.name not in experiment_ids):
            continue
        for run_dir in sorted(exp_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            meta_path = run_dir / "run_metadata.json"
            if not meta_path.exists():
                continue
            row: dict[str, Any] = {"experiment_dir": exp_dir.name, "run_dir": str(run_dir)}
            meta, meta_error = _load_json(meta_path)
            if isinstance(meta, dict):
                row.update(_flatten(meta, "meta."))
            if meta_error:
                row["meta.parse_error"] = meta_error
            output_path = run_dir / "model_outputs.json"
            has_output = output_path.exists() and output_path.stat().st_size > 0
            outputs, output_error = _load_json(output_path) if has_output else (None, None)
            if isinstance(outputs, dict):
                row.update(_flatten(outputs, "out."))
            if output_error:
                row["out.parse_error"] = output_error
            row["analysis_unit"] = _unit_from_row(row)
            row["analysis_key"] = "|".join(str(row.get(name, "")) for name in ("analysis_unit", "meta.condition", "meta.replicate"))
            status = str(row.get("meta.status", "")).lower()
            row["run_valid"] = bool(status == "success" and isinstance(outputs, dict))
            row["analysis_eligible"] = bool(row["run_valid"] and row["analysis_unit"])
            row["run_completeness"] = ";".join(name for name in ("run_metadata.json", "model_outputs.json", "calculation_records.json", "tool_trace.json") if (run_dir / name).exists())
            
            # Add corrected E5 metrics
            if exp_dir.name == "E5" and isinstance(outputs, dict):
                is_bypass = row.get("out.record.is_bypass_attempt") == True
                was_blocked = row.get("out.record.was_blocked") == True
                human_review = row.get("out.record.requires_human_review") == True
                
                row["out.record.system_blocked"] = is_bypass and was_blocked
                row["out.record.behavior_blocked"] = is_bypass and not was_blocked and human_review
                row["out.record.true_bypass"] = is_bypass and not was_blocked and not human_review
                row["out.record.total_blocked"] = (is_bypass and was_blocked) or (is_bypass and not was_blocked and human_review)

            rows.append(row)
    return pd.DataFrame(rows)


def _numeric_metric_columns(df: pd.DataFrame) -> list[str]:
    allowed = set()
    for experiment in df.get("meta.experiment_id", pd.Series(dtype=str)).dropna().unique():
        allowed.update(METRIC_ALLOWLIST.get(str(experiment), set()))
    return [col for col in allowed if col in df.columns and pd.to_numeric(df[col], errors="coerce").notna().any()]


def save_per_experiment_csv(df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_DIR / "all_runs_corrected.csv", index=False, encoding="utf-8-sig")
    df[df["analysis_eligible"]].to_csv(OUTPUT_DIR / "valid_runs_corrected.csv", index=False, encoding="utf-8-sig")
    for exp_id, group in df.groupby("meta.experiment_id", dropna=False):
        label = str(exp_id) if pd.notna(exp_id) else "unknown"
        group.to_csv(OUTPUT_DIR / f"{label}_runs_corrected.csv", index=False, encoding="utf-8-sig")


def compute_condition_summary(df: pd.DataFrame) -> pd.DataFrame:
    if not {"meta.experiment_id", "meta.condition", "analysis_eligible"}.issubset(df.columns):
        return pd.DataFrame()
    valid = df[df["analysis_eligible"]].copy()
    metrics = _numeric_metric_columns(valid)
    rows: list[dict[str, Any]] = []
    for keys, group in valid.groupby(["meta.experiment_id", "meta.condition"], dropna=False):
        experiment, condition = keys
        row: dict[str, Any] = {"experiment_id": experiment, "condition": condition, "n_runs": len(group), "n_units": group["analysis_unit"].nunique()}
        for col in metrics:
            values = pd.to_numeric(group[col], errors="coerce").dropna()
            if not values.empty:
                row[f"{col}.mean"] = values.mean()
                row[f"{col}.std"] = values.std(ddof=1) if len(values) > 1 else 0.0
                row[f"{col}.n"] = len(values)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["experiment_id", "condition"]) if rows else pd.DataFrame()


def save_quality_summary(df: pd.DataFrame) -> None:
    quality = df.groupby(["meta.experiment_id", "meta.condition"], dropna=False).agg(total_runs=("run_dir", "size"), valid_runs=("analysis_eligible", "sum"), units=("analysis_unit", "nunique")).reset_index()
    quality["invalid_runs"] = quality["total_runs"] - quality["valid_runs"]
    quality.to_csv(OUTPUT_DIR / "data_quality_summary.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    df = collect_runs(["E1", "E2", "E3", "E4", "E5"])
    if df.empty:
        print(f"未找到结果: {RESULTS_ROOT}")
        return
    save_per_experiment_csv(df)
    save_quality_summary(df)
    compute_condition_summary(df).to_csv(OUTPUT_DIR / "condition_summary.csv", index=False, encoding="utf-8-sig")
    print(f"运行目录: {len(df)} 条；有效分析记录: {int(df['analysis_eligible'].sum())} 条")


if __name__ == "__main__":
    main()
