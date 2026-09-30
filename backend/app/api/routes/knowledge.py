"""结构化知识检索接口，供 E1 检索实验使用。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.compute import formula_lib
from app.services.knowledge import loader

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_CATEGORY_MAP = {
    "公式": "formula",
    "formula": "formula",
    "材料": "material",
    "material": "material",
    "标准系列": "series",
    "series": "series",
    "标准件": "part",
    "part": "part",
}


_DOMAIN_TERMS = ("齿轮", "接触", "赫兹", "弯曲", "弯扭", "轴", "轴承", "键", "挠度", "模数", "中心距", "齿宽", "效率", "功率", "转矩", "扭转", "箱体", "壁厚", "疲劳", "强度", "寿命", "当量", "螺旋角", "轴向力", "分度圆", "直径", "标准", "系列", "螺纹", "平键", "深沟", "圆锥", "滚子", "热平衡")


def _query_terms(value: str) -> list[str]:
    terms = [term for term in _DOMAIN_TERMS if term in value]
    terms.extend(re.findall(r"(?:20CrMnTi|34CrNi3Mo|42CrMo|40Cr|45|Q235|HT200|HT250)", value))
    terms.extend(re.findall(r"GB/?T?\s*\d+(?:-\d+)?", value, flags=re.IGNORECASE))
    return list(dict.fromkeys(terms))


def _normalized_query(value: str) -> str:
    return " ".join(_query_terms(value)) or value


class KnowledgeSearchRequest(BaseModel):
    query: str = ""
    category: str = ""
    strategy: str = Field(default="keyword", pattern="^(keyword|category|exact_id|rag)$")
    limit: int = Field(default=5, ge=1, le=20)


def _terms(value: str) -> list[str]:
    return [term.lower() for term in re.split(r"[\s,，、；;：:（）()]+", value.strip()) if term]


def _formula_results(query: str, category: str, limit: int) -> list[dict[str, Any]]:
    cards = formula_lib.search_formulas(query=_normalized_query(query), category=category if category else "", limit=limit)
    return [
        {
            "id": card.id,
            "name": card.name,
            "category": card.category,
            "source": card.source,
            "expression": card.expression,
        }
        for card in cards
    ]


def _material_results(query: str, limit: int) -> list[dict[str, Any]]:
    grade_match = re.search(
        r"20CrMnTi|34CrNi3Mo|42CrMo|40Cr|45|Q235|HT200|HT250",
        query,
        flags=re.IGNORECASE,
    )
    heat_treatment = ""
    for label in ("渗碳淬火", "调质", "正火", "热轧", "铸态"):
        if label in query:
            heat_treatment = label
            break
    matches = loader.find_materials(
        grade=grade_match.group(0) if grade_match else "",
        heat_treatment=heat_treatment,
        query=_normalized_query(query),
        limit=limit,
    )
    return [
        {
            "id": item["id"],
            "name": item.get("name", ""),
            "category": "material",
            "source": item.get("standard", ""),
            "heat_treatment": item.get("heat_treatment", ""),
        }
        for item in matches
    ]


def _series_results(query: str, limit: int) -> list[dict[str, Any]]:
    terms = _terms(_normalized_query(query))
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in loader.load_series().values():
        haystack = " ".join(
            [str(item.get("id", "")), str(item.get("name", "")), str(item.get("standard", "")), str(item.get("notes", ""))]
        ).lower()
        score = sum(3 if term in str(item.get("id", "")).lower() else 1 for term in terms if term in haystack)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    return [
        {
            "id": item["id"],
            "name": item.get("name", ""),
            "category": "series",
            "source": item.get("standard", ""),
        }
        for _, item in scored[:limit]
    ]


def _part_results(query: str, limit: int) -> list[dict[str, Any]]:
    terms = _terms(_normalized_query(query))
    bore_match = re.search(r"(?:内径|轴径|直径)\s*(\d+(?:\.\d+)?)", query)
    family_id = ""
    if "键" in query:
        family_id = "key"
    elif "圆锥" in query:
        family_id = "bearing_tapered_roller"
    elif "深沟" in query or "球轴承" in query:
        family_id = "bearing_deep_groove"

    if family_id and bore_match:
        selected = loader.select_part(family_id, shaft_diameter=float(bore_match.group(1)))
        items = selected.get("candidates", [])
    else:
        items = [item for family in loader.load_part_families().values() for item in family.get("items", [])]

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        designation = str(item.get("designation", ""))
        haystack = " ".join(str(value) for value in item.values()).lower()
        score = sum(3 if term in designation.lower() else 1 for term in terms if term in haystack)
        if family_id:
            score += 2
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    return [
        {
            "id": str(item.get("designation", family_id)),
            "name": str(item.get("designation", family_id)),
            "category": "part",
            "source": loader.load_part_families().get(family_id, {}).get("standard", ""),
        }
        for _, item in scored[:limit]
    ]


def _search_exact(query: str, category: str, limit: int) -> list[dict[str, Any]]:
    needle = query.strip()
    kind = _CATEGORY_MAP.get(category, "")
    if kind in ("", "formula") and needle in formula_lib.load_formulas():
        return _formula_results(needle, "", limit)
    if kind in ("", "material") and needle in loader.load_materials():
        item = loader.get_material(needle)
        return [{"id": needle, "name": item.get("name", ""), "category": "material", "source": item.get("standard", "")}]
    if kind in ("", "series") and needle in loader.load_series():
        item = loader.get_series(needle)
        return [{"id": needle, "name": item.get("name", ""), "category": "series", "source": item.get("standard", "")}]
    if kind in ("", "part") and needle in loader.load_part_families():
        family = loader.get_part_family(needle)
        return [{"id": needle, "name": family.get("name", needle), "category": "part", "source": family.get("standard", "")}]
    all_parts = {str(item.get("designation")): item for family in loader.load_part_families().values() for item in family.get("items", [])}
    if kind in ("", "part") and needle in all_parts:
        return [{"id": needle, "name": needle, "category": "part", "source": ""}]
    return []


@router.post("/search")
def search_knowledge(request: KnowledgeSearchRequest) -> dict[str, Any]:
    kind = _CATEGORY_MAP.get(request.category, "")
    if request.strategy == "exact_id":
        results = _search_exact(request.query, request.category, request.limit)
    elif kind == "formula":
        results = _formula_results(request.query, "", request.limit)
    elif kind == "material":
        results = _material_results(request.query, request.limit)
    elif kind == "series":
        results = _series_results(request.query, request.limit)
    elif kind == "part":
        results = _part_results(request.query, request.limit)
    else:
        results = (
            _formula_results(request.query, "", request.limit)
            + _material_results(request.query, request.limit)
            + _series_results(request.query, request.limit)
            + _part_results(request.query, request.limit)
        )[: request.limit]
    return {
        "status": "ok",
        "strategy": request.strategy,
        "category": request.category,
        "query": request.query,
        "results": results,
        "result_ids": [item["id"] for item in results],
    }
