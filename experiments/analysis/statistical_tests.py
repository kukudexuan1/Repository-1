"""Statistics for experiment-specific analysis units."""
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

from framework.metrics.stats import bootstrap_ci, cliffs_delta, fisher_exact, holm_correction, wilcoxon_signed_rank
from analysis.aggregate_results import METRIC_ALLOWLIST

ANALYSIS_DIR = Path(__file__).resolve().parent
ALL_RUNS_CSV = ANALYSIS_DIR / "valid_runs_corrected.csv"


def load_data() -> pd.DataFrame:
    if not ALL_RUNS_CSV.exists():
        raise FileNotFoundError(f"汇总文件不存在: {ALL_RUNS_CSV}，请先运行 aggregate_results.py")
    return pd.read_csv(ALL_RUNS_CSV, encoding="utf-8-sig", low_memory=False)


def _baseline(conditions: list[str]) -> str | None:
    for candidate in ("B0", "B1", "C1_prompt_only", "C1_no_graph"):
        if candidate in conditions:
            return candidate
    return sorted(conditions)[0] if conditions else None


def _metric_columns(df: pd.DataFrame, experiment: str) -> list[str]:
    return [col for col in METRIC_ALLOWLIST.get(experiment, set()) if col in df.columns and pd.to_numeric(df[col], errors="coerce").notna().any()]


def _aligned(df: pd.DataFrame, condition_a: str, condition_b: str, column: str) -> tuple[list[float], list[float]]:
    keys = ["analysis_unit", "meta.replicate"]
    left = df[df["meta.condition"] == condition_a][keys + [column]].copy()
    right = df[df["meta.condition"] == condition_b][keys + [column]].copy()
    left[column] = pd.to_numeric(left[column], errors="coerce")
    right[column] = pd.to_numeric(right[column], errors="coerce")
    merged = left.merge(right, on=keys, suffixes=("_a", "_b")).dropna()
    return merged[f"{column}_a"].tolist(), merged[f"{column}_b"].tolist()


def _independent_values(df: pd.DataFrame, condition: str, column: str) -> list[float]:
    return pd.to_numeric(df.loc[df["meta.condition"] == condition, column], errors="coerce").dropna().astype(float).tolist()


def _scenario_rates(df: pd.DataFrame, condition: str, column: str) -> list[float]:
    values = df[df["meta.condition"] == condition].copy()
    values[column] = values[column].map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})
    grouped = values.dropna().groupby("analysis_unit")[column].mean()
    return grouped


def _aligned_e5(df: pd.DataFrame, condition_a: str, condition_b: str, column: str) -> tuple[list[float], list[float]]:
    left = _scenario_rates(df, condition_a, column)
    right = _scenario_rates(df, condition_b, column)
    common = sorted(set(left.index) & set(right.index))
    return [float(left[key]) for key in common], [float(right[key]) for key in common]


def _paired_result(base: list[float], current: list[float]) -> dict:
    result: dict = {"n_baseline": len(base), "n_condition": len(current), "n_paired": len(base), "mean_baseline": sum(base) / len(base), "mean_condition": sum(current) / len(current), "ci_baseline": bootstrap_ci(base), "ci_condition": bootstrap_ci(current), "absolute_difference": sum(current) / len(current) - sum(base) / len(base), "cliffs_delta": cliffs_delta(current, base)}
    stat = wilcoxon_signed_rank(current, base)
    result.update(test="Wilcoxon signed-rank", p_value=stat["p_value"], effect_r=stat.get("effect_r"))
    return result


def _e5_result(base: list[float], current: list[float]) -> dict:
    successes_base = sum(value > 0.5 for value in base)
    successes_current = sum(value > 0.5 for value in current)
    stat = fisher_exact(successes_base, len(base), successes_current, len(current))
    return {"n_baseline": len(base), "n_condition": len(current), "n_success_baseline": successes_base, "n_success_condition": successes_current, "mean_baseline": sum(base) / len(base), "mean_condition": sum(current) / len(current), "ci_baseline": bootstrap_ci(base), "ci_condition": bootstrap_ci(current), "absolute_difference": sum(current) / len(current) - sum(base) / len(base), "cliffs_delta": cliffs_delta(current, base), "test": "Fisher exact", "p_value": stat["p_value"], "odds_ratio": stat["odds_ratio"]}


def run_comparisons(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for experiment, exp_df in df.groupby("meta.experiment_id"):
        experiment = str(experiment)
        conditions = [str(x) for x in exp_df["meta.condition"].dropna().unique()]
        baseline = _baseline(conditions)
        if baseline is None:
            continue
        for column in _metric_columns(exp_df, experiment):
            for condition in conditions:
                if condition == baseline:
                    continue
                if experiment == "E5":
                    base, current = _aligned_e5(exp_df, baseline, condition, column)
                    # current values are already aligned by scenario

                else:
                    base, current = _aligned(exp_df, baseline, condition, column)
                if len(base) < 2 or len(current) < 2:
                    continue
                result = _paired_result(base, current)
                result.update({"experiment_id": experiment, "metric": column.removeprefix("out."), "column": column, "baseline_condition": baseline, "condition": condition})
                results.append(result)
    return results


def apply_holm(results: list[dict]) -> list[dict]:
    by_experiment: dict[str, list[int]] = {}
    for index, row in enumerate(results):
        by_experiment.setdefault(row["experiment_id"], []).append(index)
    for indices in by_experiment.values():
        p_values = [results[index]["p_value"] for index in indices]
        corrected = holm_correction(p_values)
        for index, value in zip(indices, corrected):
            results[index]["p_value_holm"] = value
            results[index]["significant_holm"] = value < 0.05
    return results


def main() -> None:
    df = load_data()
    results = apply_holm(run_comparisons(df))
    with (ANALYSIS_DIR / "statistical_tests_results.json").open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
    pd.DataFrame(results).to_csv(ANALYSIS_DIR / "statistical_tests_results.csv", index=False, encoding="utf-8-sig")
    print(f"有效分析记录: {len(df)} 条；生成比较: {len(results)} 条")


if __name__ == "__main__":
    main()
