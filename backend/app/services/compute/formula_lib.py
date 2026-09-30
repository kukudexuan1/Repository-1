"""设计公式库。

公式以 YAML 卡片存放，每条带符号定义、单位、适用条件与出处。求解时：
  1. 按卡片声明的单位换算输入（量纲不符直接报错，不静默通过）
  2. 用 sympy 求值或求解
  3. 若是校核公式，代入判据表达式自动判定通过与否并算出余量
  4. 产出 CalculationRecord —— 计算书章节与参数溯源都以它为准
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.calculation_record import CalcEngine, CalculationRecord, Verdict
from app.schemas.common import Quantity
from app.schemas.formula_card import FormulaCard, SymbolRole

from . import units as U

logger = logging.getLogger(__name__)

FORMULA_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "data" / "formulas"

_ASSIGN_SPLIT = re.compile(r"(?<![<>=!])=(?!=)")
_CRITERION_OPS = ("<=", ">=", "<", ">")


class FormulaError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_formulas() -> dict[str, FormulaCard]:
    import yaml

    cards: dict[str, FormulaCard] = {}
    if not FORMULA_DIR.exists():
        logger.warning("公式库目录不存在: %s", FORMULA_DIR)
        return cards

    for path in sorted(FORMULA_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except Exception as exc:  # noqa: BLE001
            logger.error("公式文件解析失败 %s: %s", path.name, exc)
            continue
        if isinstance(raw, dict):
            raw = raw.get("formulas", [])
        for item in raw:
            try:
                card = FormulaCard.model_validate(item)
            except Exception as exc:  # noqa: BLE001
                logger.error("公式卡片非法 (%s): %s", path.name, exc)
                continue
            if card.id in cards:
                logger.warning("公式 ID 重复，后者覆盖: %s", card.id)
            cards[card.id] = card
    logger.info("已加载 %d 条设计公式", len(cards))
    return cards


def reload_formulas() -> int:
    load_formulas.cache_clear()
    return len(load_formulas())


def get_formula(formula_id: str) -> FormulaCard:
    card = load_formulas().get(formula_id)
    if card is None:
        raise FormulaError(
            f"公式库中没有 ID 为 '{formula_id}' 的公式，请先用 search_formula 检索"
        )
    return card


def search_formulas(
    query: str = "", category: str = "", limit: int = 8
) -> list[FormulaCard]:
    """按关键词/类别检索公式，返回按相关度排序的候选。"""
    cards = list(load_formulas().values())
    if category:
        cards = [c for c in cards if c.category == category]
    if not query:
        return cards[:limit]

    terms = [t for t in re.split(r"[\s,，、]+", query.strip()) if t]
    scored: list[tuple[int, FormulaCard]] = []
    for card in cards:
        haystack = " ".join(
            [card.id, card.name, card.category, card.notes, " ".join(card.tags)]
        ).lower()
        score = sum(3 if t.lower() in card.name.lower() else 0 for t in terms)
        score += sum(1 for t in terms if t.lower() in haystack)
        if score:
            scored.append((score, card))
    scored.sort(key=lambda p: -p[0])
    return [c for _, c in scored[:limit]]


def categories() -> list[str]:
    return sorted({c.category for c in load_formulas().values() if c.category})


# ---------------------------------------------------------------------------
# 求解
# ---------------------------------------------------------------------------


def solve(
    formula_id: str,
    inputs: dict[str, Quantity],
    *,
    record_id: str,
    solve_for: str = "",
    title: str = "",
    extra_known: dict[str, Quantity] | None = None,
    depends_on: list[str] | None = None,
) -> CalculationRecord:
    """按公式卡片求解，返回带溯源信息的计算记录。"""
    import sympy as sp

    card = get_formula(formula_id)
    target = solve_for or (card.outputs()[0] if card.outputs() else "")
    if not target:
        raise FormulaError(f"公式 {formula_id} 未声明输出符号，无法确定求解目标")

    values, substitution_parts, used_inputs = _prepare_inputs(card, inputs)

    lhs_text, rhs_text = _split_expression(card.expression)
    local = {name: sp.Float(val) for name, val in values.items()}
    symbols = {name: sp.Symbol(name) for name in card.symbols}

    try:
        if lhs_text.strip() == target:
            expr = sp.sympify(rhs_text, locals=symbols)
            solution = expr.subs(local)
        else:
            eq = sp.Eq(
                sp.sympify(lhs_text, locals=symbols),
                sp.sympify(rhs_text, locals=symbols),
            )
            roots = sp.solve(eq.subs(local), symbols[target])
            if not roots:
                raise FormulaError(f"公式 {formula_id} 对 {target} 无解")
            solution = _pick_physical_root(roots)
        numeric = float(sp.N(solution))
    except FormulaError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FormulaError(f"公式 {formula_id} 求值失败: {exc}") from exc

    target_unit = card.symbols[target].unit if target in card.symbols else ""
    result_qty = Quantity(value=numeric, unit=target_unit)

    record = CalculationRecord(
        record_id=record_id,
        title=title or card.name,
        formula_id=card.id,
        expression=card.expression,
        inputs=used_inputs,
        substitution="；".join(substitution_parts),
        result={target: result_qty},
        criterion=card.criterion,
        source=card.source,
        engine=CalcEngine.FORMULA_LIB,
        depends_on=depends_on or [],
        notes=card.notes,
    )

    if card.is_check and card.criterion_expr:
        known = dict(values)
        known[target] = numeric
        for name, qty in (extra_known or {}).items():
            unit = card.symbols[name].unit if name in card.symbols else qty.unit
            known[name] = U.magnitude_in(qty, unit) if unit else qty.value
        verdict, margin = _evaluate_criterion(card.criterion_expr, known)
        record.verdict = verdict
        record.margin_percent = margin

    return record


def _prepare_inputs(
    card: FormulaCard, inputs: dict[str, Quantity]
) -> tuple[dict[str, float], list[str], dict[str, Quantity]]:
    values: dict[str, float] = {}
    parts: list[str] = []
    used: dict[str, Quantity] = {}

    missing = [k for k in card.required_inputs() if k not in inputs]
    if missing:
        detail = "；".join(
            f"{k}（{card.symbols[k].desc}，单位 {card.symbols[k].unit or '无量纲'}）"
            for k in missing
        )
        raise FormulaError(f"公式 {card.id} 缺少必需输入：{detail}")

    for name, spec in card.symbols.items():
        if spec.role != SymbolRole.INPUT:
            continue
        if name in inputs:
            qty = inputs[name]
            try:
                magnitude = (
                    U.magnitude_in(qty, spec.unit) if spec.unit else float(qty.value)
                )
            except U.UnitError as exc:
                raise FormulaError(
                    f"输入 {name} 单位错误：{exc}（公式要求 {spec.unit or '无量纲'}）"
                ) from exc
            values[name] = magnitude
            used[name] = qty
            shown = Quantity(value=magnitude, unit=spec.unit)
            parts.append(f"{name}={shown.render()}")
        elif spec.default is not None:
            values[name] = float(spec.default)
            used[name] = Quantity(value=float(spec.default), unit=spec.unit)
            parts.append(f"{name}={spec.default}（公式默认值）")

    unknown = set(inputs) - set(card.symbols)
    if unknown:
        raise FormulaError(
            f"公式 {card.id} 不接受这些参数：{sorted(unknown)}；"
            f"可用输入为 {card.inputs()}"
        )
    return values, parts, used


def _split_expression(expression: str) -> tuple[str, str]:
    parts = _ASSIGN_SPLIT.split(expression, maxsplit=1)
    if len(parts) != 2:
        raise FormulaError(
            f"公式表达式必须写成 '输出 = 表达式' 的形式，当前为: {expression}"
        )
    return parts[0].strip(), parts[1].strip()


def _pick_physical_root(roots: list[Any]):
    """多解时取最小正实根——机械设计中通常对应最小可行尺寸。"""
    import sympy as sp

    reals = []
    for root in roots:
        try:
            val = complex(sp.N(root))
        except Exception:  # noqa: BLE001
            continue
        if abs(val.imag) < 1e-9:
            reals.append((val.real, root))
    positives = [r for r in reals if r[0] > 0]
    pool = positives or reals
    if not pool:
        raise FormulaError("求解结果中没有实数解")
    pool.sort(key=lambda p: p[0])
    return pool[0][1]


def _evaluate_criterion(
    criterion_expr: str, known: dict[str, float]
) -> tuple[Verdict, float | None]:
    import sympy as sp

    op = next((o for o in _CRITERION_OPS if o in criterion_expr), "")
    if not op:
        return Verdict.NOT_APPLICABLE, None

    left_text, right_text = criterion_expr.split(op, 1)
    symbols = {name: sp.Symbol(name) for name in known}
    try:
        left = float(sp.N(sp.sympify(left_text, locals=symbols).subs(known)))
        right = float(sp.N(sp.sympify(right_text, locals=symbols).subs(known)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("判据 '%s' 无法求值: %s", criterion_expr, exc)
        return Verdict.NOT_APPLICABLE, None

    passed = {
        "<=": left <= right,
        "<": left < right,
        ">=": left >= right,
        ">": left > right,
    }[op]

    margin = None
    reference = right if op in ("<=", "<") else left
    if reference:
        margin = abs(reference - (left if op in ("<=", "<") else right)) / abs(reference) * 100.0

    return (Verdict.PASS if passed else Verdict.FAIL), margin
