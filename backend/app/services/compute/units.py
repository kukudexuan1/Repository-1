"""单位与量纲。

设计系统里所有数值都带单位流转，换算与量纲一致性由本模块统一负责——把
「mm 还是 cm」这类问题从提示词纪律变成机制约束。
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.schemas.common import Quantity

logger = logging.getLogger(__name__)


class UnitError(ValueError):
    """单位无法识别或量纲不匹配。"""


# 工程常用别名 → pint 可识别写法
_ALIASES = {
    "": "dimensionless",
    "-": "dimensionless",
    "1": "dimensionless",
    "无量纲": "dimensionless",
    "r/min": "revolutions_per_minute",
    "rpm": "revolutions_per_minute",
    "转/分": "revolutions_per_minute",
    "N*mm": "newton * millimeter",
    "N·mm": "newton * millimeter",
    "N*m": "newton * meter",
    "N·m": "newton * meter",
    "N/mm2": "newton / millimeter ** 2",
    "N/mm^2": "newton / millimeter ** 2",
    "N/mm**2": "newton / millimeter ** 2",
    "kgf": "kilogram_force",
    "°": "degree",
    "度": "degree",
    "h": "hour",
    "小时": "hour",
    "MPa**0.5": "megapascal ** 0.5",
    "MPa^0.5": "megapascal ** 0.5",
    "sqrt(MPa)": "megapascal ** 0.5",
}


@lru_cache(maxsize=1)
def _registry():
    try:
        import pint
    except ImportError as exc:  # pragma: no cover
        raise UnitError(
            "缺少 pint 依赖，无法做量纲校验。请先 pip install pint"
        ) from exc
    reg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
    reg.default_format = "~P"
    return reg


def normalize_unit(unit: str) -> str:
    unit = (unit or "").strip()
    return _ALIASES.get(unit, unit or "dimensionless")


def to_pint(qty: Quantity):
    """Quantity → pint.Quantity。"""
    reg = _registry()
    unit = normalize_unit(qty.unit)
    try:
        return qty.value * reg(unit)
    except Exception as exc:  # noqa: BLE001 - pint 抛出的异常类型较杂
        raise UnitError(f"无法识别单位 '{qty.unit}': {exc}") from exc


def from_pint(pq, unit_label: str = "") -> Quantity:
    """pint.Quantity → Quantity。unit_label 为空则用 pint 的紧凑表示。"""
    label = unit_label or f"{pq.units:~P}"
    if label in ("dimensionless", ""):
        label = ""
    return Quantity(value=float(pq.magnitude), unit=label)


def convert(qty: Quantity, target_unit: str) -> Quantity:
    """把 Quantity 换算到目标单位，量纲不符时报错而非静默通过。"""
    reg = _registry()
    target = normalize_unit(target_unit)
    try:
        converted = to_pint(qty).to(reg(target).units)
    except UnitError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UnitError(
            f"量纲不匹配：{qty.render()} 无法换算为 '{target_unit}'（{exc}）"
        ) from exc
    return Quantity(value=float(converted.magnitude), unit=target_unit)


def magnitude_in(qty: Quantity, target_unit: str) -> float:
    """取 Quantity 在目标单位下的裸数值，供计算使用。"""
    return convert(qty, target_unit).value


def check_compatible(qty: Quantity, expected_unit: str) -> None:
    """只校验量纲兼容性，不做换算。"""
    if not expected_unit:
        return
    convert(qty, expected_unit)


def parse(text: str) -> Quantity:
    """解析 '30 mm' / '4kW' / '1440 r/min' 这类字符串。"""
    reg = _registry()
    raw = (text or "").strip()
    if not raw:
        raise UnitError("空字符串无法解析为物理量")
    try:
        pq = reg.Quantity(raw)
    except Exception as exc:  # noqa: BLE001
        raise UnitError(f"无法解析物理量 '{text}': {exc}") from exc
    return from_pint(pq)


def coerce(value: Quantity | float | int | str, unit: str = "") -> Quantity:
    """把各种输入形态统一成 Quantity。"""
    if isinstance(value, Quantity):
        return value
    if isinstance(value, (int, float)):
        return Quantity(value=float(value), unit=unit)
    if isinstance(value, dict):
        return Quantity.model_validate(value)
    qty = parse(str(value))
    if unit:
        return convert(qty, unit)
    return qty


def units_available() -> bool:
    """pint 是否可用。用于运行时自检。"""
    try:
        _registry()
        return True
    except UnitError:
        return False
