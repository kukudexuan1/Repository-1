"""设计知识库加载与查询。

材料、标准尺寸系列、标准件、设计任务书模板都以 YAML 存放，便于版本控制与人工
审阅。所有查询结果都带 standard 字段（国标号或手册出处），这样参数落账时的
basis 天然有据可查。
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).with_name("data")
MATERIAL_DIR = DATA_DIR / "materials"
STANDARD_DIR = DATA_DIR / "standards"
SPEC_TEMPLATE_DIR = DATA_DIR / "spec_templates"


class KnowledgeError(ValueError):
    pass


def _load_yaml(path: Path) -> Any:
    import yaml

    if not path.exists():
        raise KnowledgeError(f"知识库文件不存在: {path.name}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_yaml(directory: Path):
    if not directory.exists():
        logger.warning("知识库目录不存在: %s", directory)
        return
    for path in sorted(directory.glob("*.yaml")):
        try:
            yield path, _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            logger.error("知识库文件解析失败 %s: %s", path.name, exc)


# ---------------------------------------------------------------------------
# 材料
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_materials() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path, raw in _iter_yaml(MATERIAL_DIR):
        items = raw.get("materials", []) if isinstance(raw, dict) else raw or []
        for item in items:
            key = item.get("id")
            if not key:
                logger.error("材料条目缺少 id (%s)", path.name)
                continue
            out[key] = item
    logger.info("已加载 %d 种材料", len(out))
    return out


def find_materials(
    grade: str = "", heat_treatment: str = "", query: str = "", limit: int = 6
) -> list[dict[str, Any]]:
    """按牌号/热处理/关键词检索材料。"""
    materials = list(load_materials().values())
    results = materials

    if grade:
        needle = grade.strip().lower()
        results = [
            m for m in results if needle in str(m.get("grade", "")).lower()
        ] or [m for m in materials if needle in str(m.get("name", "")).lower()]

    if heat_treatment:
        needle = heat_treatment.strip()
        narrowed = [m for m in results if needle in str(m.get("heat_treatment", ""))]
        if narrowed:
            results = narrowed

    if query and not grade:
        terms = [t for t in re.split(r"[\s,，、]+", query.strip()) if t]
        scored = []
        for mat in results:
            hay = " ".join(
                [
                    str(mat.get("name", "")),
                    str(mat.get("grade", "")),
                    str(mat.get("category", "")),
                    str(mat.get("notes", "")),
                    " ".join(mat.get("applications", []) or []),
                ]
            )
            score = sum(1 for t in terms if t in hay)
            if score:
                scored.append((score, mat))
        if scored:
            scored.sort(key=lambda p: -p[0])
            results = [m for _, m in scored]

    return results[:limit]


def get_material(material_id: str) -> dict[str, Any]:
    mat = load_materials().get(material_id)
    if mat is None:
        raise KnowledgeError(
            f"材料库中没有 id 为 '{material_id}' 的材料。"
            f"可用：{sorted(load_materials().keys())}"
        )
    return mat


# ---------------------------------------------------------------------------
# 标准尺寸系列
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_series() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for _, raw in _iter_yaml(STANDARD_DIR):
        if not isinstance(raw, dict):
            continue
        for item in raw.get("series", []) or []:
            key = item.get("id")
            if key:
                out[key] = item
    logger.info("已加载 %d 个标准尺寸系列", len(out))
    return out


def get_series(series_id: str) -> dict[str, Any]:
    series = load_series().get(series_id)
    if series is None:
        raise KnowledgeError(
            f"没有名为 '{series_id}' 的标准系列。可用：{sorted(load_series().keys())}"
        )
    return series


def round_to_series(
    series_id: str, value: float, direction: str = ""
) -> dict[str, Any]:
    """把计算值圆整到标准系列。

    direction: up 向上取 / down 向下取 / nearest 取最近 / 空则用系列默认策略。
    """
    series = get_series(series_id)
    values: list[float] = [float(v) for v in series.get("values", [])]
    if not values:
        raise KnowledgeError(f"标准系列 {series_id} 没有数值")

    mode = direction or series.get("prefer", "up")
    values.sort()

    if mode == "up":
        chosen = next((v for v in values if v >= value), values[-1])
    elif mode == "down":
        candidates = [v for v in values if v <= value]
        chosen = candidates[-1] if candidates else values[0]
    else:
        chosen = min(values, key=lambda v: abs(v - value))

    out_of_range = value > values[-1] or value < values[0]
    return {
        "series_id": series_id,
        "series_name": series.get("name", ""),
        "standard": series.get("standard", ""),
        "unit": series.get("unit", ""),
        "raw_value": value,
        "rounded_value": chosen,
        "direction": mode,
        "out_of_range": out_of_range,
        "notes": series.get("notes", ""),
        "neighbors": _neighbors(values, chosen),
    }


def _neighbors(values: list[float], chosen: float) -> list[float]:
    idx = values.index(chosen)
    lo = max(0, idx - 1)
    hi = min(len(values), idx + 2)
    return values[lo:hi]


# ---------------------------------------------------------------------------
# 标准件
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_part_families() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for _, raw in _iter_yaml(STANDARD_DIR):
        if not isinstance(raw, dict):
            continue
        for item in raw.get("part_families", []) or []:
            key = item.get("id")
            if key:
                out[key] = item
    logger.info("已加载 %d 个标准件族", len(out))
    return out


def get_part_family(family_id: str) -> dict[str, Any]:
    family = load_part_families().get(family_id)
    if family is None:
        raise KnowledgeError(
            f"没有名为 '{family_id}' 的标准件族。"
            f"可用：{sorted(load_part_families().keys())}"
        )
    return family


def select_part(
    family_id: str,
    *,
    shaft_diameter: float | None = None,
    min_dynamic_load: float | None = None,
    belt_type: str = "",
    max_candidates: int = 5,
) -> dict[str, Any]:
    """按轴径与承载要求筛选标准件候选。"""
    family = get_part_family(family_id)
    items: list[dict[str, Any]] = list(family.get("items", []))
    if belt_type:
        needle = belt_type.strip().lower()
        items = [
            it for it in items
            if needle in str(it.get("belt_type", it.get("section", ""))).lower()
        ]
    select_by = family.get("select_by", "")
    matched = items

    if shaft_diameter is not None:
        if select_by == "shaft_diameter":
            matched = [
                it
                for it in items
                if float(it.get("d_min", 0)) < shaft_diameter <= float(it.get("d_max", 0))
            ]
        elif select_by == "bore_diameter":
            matched = [
                it for it in items if abs(float(it.get("d", -1)) - shaft_diameter) < 1e-6
            ]
            if not matched:
                matched = [it for it in items if float(it.get("d", 0)) >= shaft_diameter]
                matched.sort(key=lambda it: float(it.get("d", 0)))

    if select_by == "nominal_diameter" and shaft_diameter is not None:
        matched = [
            it for it in items
            if float(it.get("d", it.get("thread", 0))) >= shaft_diameter
        ]
        matched.sort(key=lambda it: float(it.get("d", it.get("thread", 0))))

    if select_by == "nominal_thread" and shaft_diameter is not None:
        matched = [
            it for it in items
            if float(it.get("thread", 0)) >= shaft_diameter
        ]
        matched.sort(key=lambda it: float(it.get("thread", 0)))

    if select_by == "transmitted_torque" and min_dynamic_load is not None:
        matched = [
            it for it in items
            if float(it.get("rated_torque", 0)) >= min_dynamic_load
        ]
        matched.sort(key=lambda it: float(it.get("rated_torque", 0)))

    if min_dynamic_load is not None:
        matched = [
            it for it in matched if float(it.get("C_r", 0)) >= min_dynamic_load
        ]
        matched.sort(key=lambda it: float(it.get("C_r", 0)))

    return {
        "family_id": family_id,
        "family_name": family.get("name", ""),
        "standard": family.get("standard", ""),
        "units": family.get("units", {}),
        "life_exponent": family.get("life_exponent"),
        "length_series": family.get("length_series"),
        "notes": family.get("notes", ""),
        "candidates": matched[:max_candidates],
        "candidate_count": len(matched),
    }


# ---------------------------------------------------------------------------
# 设计任务书模板
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_spec_templates() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path, raw in _iter_yaml(SPEC_TEMPLATE_DIR):
        if not isinstance(raw, dict):
            continue
        key = raw.get("family") or path.stem
        out[key] = raw
    logger.info("已加载 %d 个设计任务书模板", len(out))
    return out


def get_spec_template(family: str) -> dict[str, Any]:
    template = load_spec_templates().get(family)
    if template is None:
        raise KnowledgeError(
            f"没有零件族 '{family}' 的设计任务书模板。"
            f"可用：{sorted(load_spec_templates().keys())}"
        )
    return template


def available_families() -> list[dict[str, str]]:
    return [
        {
            "family": key,
            "label": tpl.get("family_label", key),
            "description": (tpl.get("description") or "").strip(),
        }
        for key, tpl in load_spec_templates().items()
    ]


def reload_all() -> dict[str, int]:
    for fn in (
        load_materials,
        load_series,
        load_part_families,
        load_spec_templates,
    ):
        fn.cache_clear()
    return {
        "materials": len(load_materials()),
        "series": len(load_series()),
        "part_families": len(load_part_families()),
        "spec_templates": len(load_spec_templates()),
    }
