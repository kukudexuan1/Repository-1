"""参数台账服务：溯源校验与变更失效传播。

两个职责：
  1. 落账前强制校验依据（铁律二）——计算得来的参数必须指向计算记录，
     查表得来的必须指向标准号，凭空数字进不了台账。
  2. 参数变更时沿依赖图传播失效标记，让「改一个参数要重算哪些结论」变成
     系统能回答的问题，而不是靠人记。
"""

from __future__ import annotations

import logging

from app.schemas.calculation_record import CalculationRecord
from app.schemas.common import Quantity
from app.schemas.parameter_ledger import (
    SOURCES_WITHOUT_CALC,
    ParameterEntry,
    ParameterSource,
    ParameterStatus,
)
from app.schemas.session_state import SessionState

from . import units as U

logger = logging.getLogger(__name__)

CALC_PREFIX = "calc#"


class LedgerError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 落账
# ---------------------------------------------------------------------------


def commit_parameter(
    session: SessionState,
    *,
    symbol: str,
    value: Quantity,
    source: ParameterSource,
    name: str = "",
    basis: list[str] | None = None,
    rationale: str = "",
    group: str = "其他",
    propagation_mode: str = "recursive",
    evidence_required: bool = True,
) -> ParameterEntry:
    """把一个参数写入台账，落账前做溯源校验。"""
    basis = [b.strip() for b in (basis or []) if b.strip()]

    if session.ledger.is_frozen:
        raise LedgerError(
            "台账已冻结，不能直接修改参数。若确需返工，请先说明原因并请用户确认解冻"
        )

    if evidence_required:
        _validate_basis(session, symbol, source, basis, rationale)
    elif source in (ParameterSource.DESIGN_CHOICE, ParameterSource.ASSUMED) and not (rationale or basis):
        pass
    _validate_unit(symbol, value)

    existing = session.ledger.get(symbol)
    changed_value = existing is not None and _differs(existing.value, value)

    entry = session.ledger.commit(
        symbol,
        value,
        source,
        name=name,
        basis=basis,
        rationale=rationale,
        group=group,
    )

    if changed_value and propagation_mode != "none":
        invalidator = {
            "direct": invalidate_direct,
            "full": invalidate_all,
            "recursive": invalidate_from,
        }.get(propagation_mode)
        if invalidator is None:
            raise LedgerError(f"未知失效传播模式: {propagation_mode}")
        affected = invalidator(
            session,
            symbol,
            reason=f"{symbol} 由 {entry.superseded_value} 改为 {value.render()}",
        )
        if affected:
            logger.info("参数 %s 变更导致 %d 项结论失效", symbol, len(affected))
    return entry


def _validate_basis(
    session: SessionState,
    symbol: str,
    source: ParameterSource,
    basis: list[str],
    rationale: str,
) -> None:
    if source in SOURCES_WITHOUT_CALC:
        if source in (ParameterSource.DESIGN_CHOICE, ParameterSource.ASSUMED) and not (
            rationale or basis
        ):
            raise LedgerError(
                f"参数 {symbol} 的来源是 {source.value}，必须填写 rationale 说明取值理由"
            )
        return

    if not basis:
        raise LedgerError(
            f"参数 {symbol} 的来源是 {source.value}，basis 不能为空："
            "计算所得须填计算记录 ID（如 calc#7），查表所得须填标准号（如 GB/T 1357-2008）"
        )

    if source == ParameterSource.CALCULATED:
        calc_refs = [b for b in basis if b.startswith(CALC_PREFIX)]
        if not calc_refs:
            raise LedgerError(
                f"参数 {symbol} 声明为 calculated，basis 中必须至少有一条 "
                f"'{CALC_PREFIX}N' 形式的计算记录引用。"
                "若这个数是你自己算的，请先用 solve_formula 或 run_calculation 留下记录"
            )
        missing = [ref for ref in calc_refs if ref not in session.calculations]
        if missing:
            raise LedgerError(
                f"参数 {symbol} 引用了不存在的计算记录 {missing}。"
                f"当前已有记录：{sorted(session.calculations.keys()) or '（无）'}"
            )


def _validate_unit(symbol: str, value: Quantity) -> None:
    if not value.unit:
        return
    try:
        U.check_compatible(value, value.unit)
    except U.UnitError as exc:
        raise LedgerError(f"参数 {symbol} 的单位无法识别：{exc}") from exc


def _differs(old: Quantity, new: Quantity, rel_tol: float = 1e-9) -> bool:
    if old.unit != new.unit:
        try:
            new = U.convert(new, old.unit)
        except U.UnitError:
            return True
    denom = abs(old.value) or 1.0
    return abs(old.value - new.value) / denom > rel_tol


# ---------------------------------------------------------------------------
# 失效传播
# ---------------------------------------------------------------------------


def invalidate_direct(session: SessionState, symbol: str, reason: str) -> list[str]:
    affected: list[str] = []
    for record in session.calculations.values():
        if not record.stale and symbol in record.depends_on:
            record.stale = True
            record.stale_reason = f"依赖项 {symbol} 已变更（{reason}）"
            affected.append(record.record_id)
    for entry in session.ledger.entries.values():
        if entry.symbol != symbol and entry.status != ParameterStatus.STALE and symbol in entry.basis:
            session.ledger.mark_stale(entry.symbol, f"依据 {symbol} 已失效（{reason}）")
            affected.append(entry.symbol)
    return affected


def invalidate_all(session: SessionState, symbol: str, reason: str) -> list[str]:
    affected: list[str] = []
    for record in session.calculations.values():
        if not record.stale:
            record.stale = True
            record.stale_reason = f"输入 {symbol} 已变更，执行全量失效（{reason}）"
            affected.append(record.record_id)
    for entry in session.ledger.entries.values():
        if entry.symbol != symbol and entry.status != ParameterStatus.STALE:
            session.ledger.mark_stale(entry.symbol, f"输入 {symbol} 已变更，执行全量失效（{reason}）")
            affected.append(entry.symbol)
    return affected


def invalidate_from(session: SessionState, symbol: str, reason: str) -> list[str]:
    """参数变更后沿依赖图标记失效，返回受影响的计算记录与参数标识。"""
    affected: list[str] = []
    pending = {symbol}
    seen: set[str] = set()

    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)

        for record in session.calculations.values():
            if record.stale or current not in record.depends_on:
                continue
            record.stale = True
            record.stale_reason = f"依赖项 {current} 已变更（{reason}）"
            affected.append(record.record_id)
            pending.add(record.record_id)

        for entry in session.ledger.entries.values():
            if entry.symbol == current or entry.status == ParameterStatus.STALE:
                continue
            if current in entry.basis:
                session.ledger.mark_stale(
                    entry.symbol, f"依据 {current} 已失效（{reason}）"
                )
                affected.append(entry.symbol)
                pending.add(entry.symbol)

    return affected


def stale_summary(session: SessionState) -> dict[str, list[str]]:
    return {
        "stale_calculations": [
            r.record_id for r in session.calculations.values() if r.stale
        ],
        "stale_parameters": [e.symbol for e in session.ledger.stale()],
    }


# ---------------------------------------------------------------------------
# 取值（供建模契约生成使用）
# ---------------------------------------------------------------------------


def resolve_for_geometry(
    session: SessionState, symbol: str, target_unit: str = ""
) -> Quantity:
    """取台账中可用于几何表达的参数值。

    状态未达 confirmed 的参数一律拒绝，这是「几何尺寸必须有据」的执行点。
    """
    entry = session.ledger.get(symbol)
    if entry is None:
        raise LedgerError(
            f"台账中没有参数 '{symbol}'。几何尺寸必须先经 commit_parameter 落账，"
            f"当前台账包含：{sorted(session.ledger.entries.keys()) or '（空）'}"
        )
    if entry.status == ParameterStatus.STALE:
        raise LedgerError(
            f"参数 {symbol} 已失效（{entry.stale_reason}），请重算后再用于建模"
        )
    if not entry.usable_for_geometry:
        raise LedgerError(
            f"参数 {symbol} 当前状态为 {entry.status.value}，尚未确认，不能用于建模。"
            "请先完成校核并请用户确认冻结"
        )
    if target_unit:
        return U.convert(entry.value, target_unit)
    return entry.value


def record_calculation(
    session: SessionState, record: CalculationRecord
) -> CalculationRecord:
    """登记计算记录，并把它依赖的参数补进依赖图。"""
    for name in record.inputs:
        if name in session.ledger.entries and name not in record.depends_on:
            record.depends_on.append(name)
    return session.add_calculation(record)
