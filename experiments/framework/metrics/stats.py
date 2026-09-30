"""
stats.py — 统计检验与效应量。

协议 §7 规范：
- 两配对条件：Wilcoxon signed-rank test
- 两独立比例：Fisher exact test
- 多条件比较：Friedman test + Holm 校正
- 效应量：Cliff's delta / rank-biserial correlation
- 置信区间：bootstrap 95% CI（配对）或 Wilson CI（比例）
"""

from __future__ import annotations

import math
import random
from typing import Any


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank test（配对，两条件）
# ---------------------------------------------------------------------------

def wilcoxon_signed_rank(x: list[float], y: list[float]) -> dict[str, Any]:
    """
    两配对条件的 Wilcoxon signed-rank test。
    返回 W 统计量、近似 p 值（正态近似）和效应量 r。
    """
    if len(x) != len(y):
        raise ValueError("x 和 y 长度不一致")
    diffs = [xi - yi for xi, yi in zip(x, y)]
    nonzero = [(abs(d), math.copysign(1, d)) for d in diffs if d != 0]
    if not nonzero:
        return {"W": 0.0, "p_value": 1.0, "effect_r": 0.0, "n": len(x)}

    nonzero.sort(key=lambda t: t[0])
    n = len(nonzero)
    # 处理并列秩
    ranks = _tied_ranks([t[0] for t in nonzero])
    W_plus = sum(r for r, (_, sign) in zip(ranks, nonzero) if sign > 0)
    W_minus = sum(r for r, (_, sign) in zip(ranks, nonzero) if sign < 0)
    W = min(W_plus, W_minus)

    # 正态近似（n >= 10 时可靠）
    mean_W = n * (n + 1) / 4
    std_W = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (W - mean_W) / std_W if std_W > 0 else 0.0
    p_value = 2 * _norm_cdf(-abs(z))
    effect_r = z / math.sqrt(n)

    return {
        "W": round(W, 4),
        "z": round(z, 4),
        "p_value": round(p_value, 6),
        "effect_r": round(effect_r, 4),
        "n_nonzero": n,
        "n_total": len(x),
    }


# ---------------------------------------------------------------------------
# Fisher exact test（两独立比例）
# ---------------------------------------------------------------------------

def fisher_exact(
    n_a_success: int, n_a: int, n_b_success: int, n_b: int
) -> dict[str, Any]:
    """
    Fisher exact test，双尾。
    返回 odds ratio 和 p 值。
    """
    a, b = n_a_success, n_a - n_a_success
    c, d = n_b_success, n_b - n_b_success
    if a < 0 or b < 0 or c < 0 or d < 0:
        raise ValueError("计数不能为负")

    p_value = _fisher_p(a, b, c, d)
    or_val = (a * d) / (b * c) if b > 0 and c > 0 else float("inf")

    return {
        "odds_ratio": round(or_val, 4),
        "p_value": round(p_value, 6),
        "table": [[a, b], [c, d]],
    }


def _fisher_p(a: int, b: int, c: int, d: int) -> float:
    """双尾 Fisher exact p 值（超几何分布精确计算）。"""
    n = a + b + c + d
    row1 = a + b
    col1 = a + c

    # 计算观测值的对数超几何概率
    def log_hyper(k: int) -> float:
        return (
            _log_comb(row1, k)
            + _log_comb(n - row1, col1 - k)
            - _log_comb(n, col1)
        )

    obs_log_p = log_hyper(a)
    p_val = 0.0
    k_min = max(0, col1 - (n - row1))
    k_max = min(row1, col1)
    for k in range(k_min, k_max + 1):
        lp = log_hyper(k)
        if lp <= obs_log_p + 1e-10:
            p_val += math.exp(lp)
    return min(1.0, p_val)


def _log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


# ---------------------------------------------------------------------------
# Friedman test（多条件比较）
# ---------------------------------------------------------------------------

def friedman_test(data: list[list[float]]) -> dict[str, Any]:
    """
    Friedman test：data[i] = 第 i 个 block（任务）在各条件下的观测值。
    返回 chi2 统计量和 p 值（卡方近似）。
    """
    n = len(data)       # block 数
    k = len(data[0])    # 条件数
    if n < 2 or k < 2:
        return {"chi2": 0.0, "p_value": 1.0, "n": n, "k": k}

    # 对每个 block 内部排秩
    ranked = []
    for row in data:
        ranks = _tied_ranks(row)
        ranked.append(ranks)

    # Friedman 统计量
    col_rank_sums = [sum(ranked[i][j] for i in range(n)) for j in range(k)]
    chi2 = (
        12 / (n * k * (k + 1))
        * sum(s**2 for s in col_rank_sums)
        - 3 * n * (k + 1)
    )
    p_value = _chi2_sf(chi2, k - 1)

    return {
        "chi2": round(chi2, 4),
        "p_value": round(p_value, 6),
        "n_blocks": n,
        "k_conditions": k,
        "rank_sums": [round(s, 2) for s in col_rank_sums],
    }


# ---------------------------------------------------------------------------
# Holm 校正
# ---------------------------------------------------------------------------

def holm_correction(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni 校正，返回与输入等长的校正后 p 值列表。"""
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda t: t[1])
    corrected = [0.0] * n
    for rank, (orig_idx, p) in enumerate(indexed):
        corrected[orig_idx] = min(1.0, p * (n - rank))
    # 单调性保证
    for i in range(1, n):
        corrected[indexed[i][0]] = max(
            corrected[indexed[i][0]], corrected[indexed[i - 1][0]]
        )
    return [round(v, 6) for v in corrected]


# ---------------------------------------------------------------------------
# Cliff's delta（效应量）
# ---------------------------------------------------------------------------

def cliffs_delta(x: list[float], y: list[float]) -> float:
    """
    Cliff's delta = (P(x > y) - P(x < y))。
    范围 [-1, 1]；|d| < 0.147 小，0.147-0.33 中，>0.474 大。
    """
    n_x, n_y = len(x), len(y)
    if n_x == 0 or n_y == 0:
        return 0.0
    greater = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    return round((greater - less) / (n_x * n_y), 4)


# ---------------------------------------------------------------------------
# Bootstrap CI（配对指标）
# ---------------------------------------------------------------------------

def bootstrap_ci(
    values: list[float],
    stat_fn=None,
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    单样本 bootstrap 置信区间（percentile method）。
    stat_fn 默认为均值。
    """
    if not values:
        return 0.0, 0.0
    if stat_fn is None:
        def stat_fn(v):
            return sum(v) / len(v)

    rng = random.Random(seed)
    n = len(values)
    boot_stats = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boot_stats.append(stat_fn(sample))
    boot_stats.sort()
    alpha = 1 - ci
    lo = boot_stats[int(n_boot * alpha / 2)]
    hi = boot_stats[int(n_boot * (1 - alpha / 2))]
    return round(lo, 4), round(hi, 4)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _tied_ranks(values: list[float]) -> list[float]:
    """并列秩平均处理。"""
    n = len(values)
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and values[indexed[j + 1]] == values[indexed[j]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def _norm_cdf(z: float) -> float:
    """标准正态 CDF（近似）。"""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _chi2_sf(x: float, df: int) -> float:
    """卡方分布生存函数（上尾概率），正则化不完全伽玛函数近似。"""
    if x <= 0:
        return 1.0
    return _regularized_upper_gamma(df / 2, x / 2)


def _regularized_upper_gamma(a: float, x: float) -> float:
    """正则化上不完全伽玛函数 Q(a, x)，级数展开近似。"""
    if x < 0:
        return 1.0
    # 使用连分数展开（x > a+1 时收敛快）或级数展开
    if x < a + 1:
        return 1.0 - _gamma_series(a, x)
    return _gamma_cf(a, x)


def _gamma_series(a: float, x: float, max_iter: int = 200) -> float:
    if x == 0:
        return 0.0
    ap = a
    s = term = 1.0 / a
    for _ in range(max_iter):
        ap += 1
        term *= x / ap
        s += term
        if abs(term) < abs(s) * 1e-10:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float, max_iter: int = 200) -> float:
    b = x + 1.0 - a
    c = 1.0 / 1e-300
    d = 1.0 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
