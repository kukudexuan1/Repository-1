"""Effect sizes based on matched experiment units."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ImportError:
    print("缺少 pandas，请运行: pip install pandas")
    sys.exit(1)

from framework.metrics.stats import bootstrap_ci, cliffs_delta, wilcoxon_signed_rank
from analysis.aggregate_results import METRIC_ALLOWLIST

ANALYSIS_DIR = Path(__file__).resolve().parent
ALL_RUNS_CSV = ANALYSIS_DIR / "valid_runs_corrected.csv"
TABLES_DIR = Path(__file__).resolve().parents[1] / "tables"


def load_data() -> pd.DataFrame:
    if not ALL_RUNS_CSV.exists():
        raise FileNotFoundError(f"汇总文件不存在: {ALL_RUNS_CSV}，请先运行 aggregate_results.py")
    return pd.read_csv(ALL_RUNS_CSV, encoding="utf-8-sig", low_memory=False)


def _baseline(conditions: list[str]) -> str | None:
    for candidate in ("B0", "B1", "C1_prompt_only", "C1_no_graph"):
        if candidate in conditions:
            return candidate
    return sorted(conditions)[0] if conditions else None


def _columns(df: pd.DataFrame, experiment: str) -> list[str]:
    return [col for col in METRIC_ALLOWLIST.get(experiment, set()) if col in df.columns and pd.to_numeric(df[col], errors="coerce").notna().any()]


def _values(df: pd.DataFrame, baseline: str, condition: str, column: str, paired: bool) -> tuple[list[float], list[float]]:
    if not paired:
        base_map = df[df["meta.condition"] == baseline].groupby("analysis_unit")[column].mean().dropna().to_dict()
        current_map = df[df["meta.condition"] == condition].groupby("analysis_unit")[column].mean().dropna().to_dict()
        common = sorted(set(base_map) & set(current_map))
        return [float(base_map[key]) for key in common], [float(current_map[key]) for key in common]
    keys = ["analysis_unit", "meta.replicate"]
    left = df[df["meta.condition"] == baseline][keys + [column]].copy()
    right = df[df["meta.condition"] == condition][keys + [column]].copy()
    left[column] = pd.to_numeric(left[column], errors="coerce")
    right[column] = pd.to_numeric(right[column], errors="coerce")
    merged = left.merge(right, on=keys, suffixes=("_base", "_current")).dropna()
    return merged[f"{column}_base"].tolist(), merged[f"{column}_current"].tolist()


def _magnitude(delta: float) -> str:
    value = abs(delta)
    return "large" if value > 0.474 else "medium" if value > 0.33 else "small" if value > 0.147 else "negligible"


def compute_all_effect_sizes(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for experiment, exp_df in df.groupby("meta.experiment_id"):
        experiment = str(experiment)
        conditions = [str(x) for x in exp_df["meta.condition"].dropna().unique()]
        baseline = _baseline(conditions)
        if baseline is None:
            continue
        for column in _columns(exp_df, experiment):
            for condition in conditions:
                if condition == baseline:
                    continue
                paired = experiment != "E5"
                base, current = _values(exp_df, baseline, condition, column, paired)
                if len(base) < 2 or len(current) < 2:
                    continue
                base_mean = sum(base) / len(base)
                current_mean = sum(current) / len(current)
                delta = cliffs_delta(current, base)
                diff = current_mean - base_mean
                row = {"experiment_id": experiment, "metric": column.removeprefix("out."), "column": column, "baseline_condition": baseline, "condition": condition, "analysis_design": "paired" if paired else "independent_proportions", "n_baseline": len(base), "n_condition": len(current), "n_paired": len(base) if paired else None, "mean_baseline": round(base_mean, 6), "mean_condition": round(current_mean, 6), "ci_baseline": bootstrap_ci(base), "ci_condition": bootstrap_ci(current), "absolute_difference": round(diff, 6), "relative_difference": round(diff / abs(base_mean), 6) if base_mean else None, "cliffs_delta": delta, "effect_magnitude": _magnitude(delta)}
                if paired:
                    row["paired_effect_r"] = wilcoxon_signed_rank(current, base).get("effect_r", 0.0)
                results.append(row)
    return results


def main() -> None:
    df = load_data()
    results = compute_all_effect_sizes(df)
    TABLES_DIR.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(TABLES_DIR / "effect_sizes.csv", index=False, encoding="utf-8-sig")
    with (ANALYSIS_DIR / "effect_sizes_results.json").open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
    print(f"有效分析记录: {len(df)} 条；生成效应量: {len(results)} 条")


if __name__ == "__main__":
    main()
