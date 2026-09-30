"""知识层工具：查公式、查材料、查标准系列、查标准件。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.compute import formula_lib
from app.services.knowledge import loader

from .registry import ToolContext, ToolLayer, ToolRefusal, register


class SearchFormulaArgs(BaseModel):
    query: str = Field(
        default="",
        description="检索关键词，如 '齿面接触疲劳强度设计'、'轴承寿命'、'键 挤压'",
    )
    category: str = Field(
        default="",
        description="限定类别：overall(总体设计) / gear(齿轮) / shaft(轴) / key(键) / bearing(轴承) / housing(箱体)",
    )
    formula_id: str = Field(
        default="", description="已知公式 ID 时直接取该条公式的完整说明"
    )


@register(
    "search_formula",
    layer=ToolLayer.KNOWLEDGE,
    args_model=SearchFormulaArgs,
    description=(
        "检索设计公式库，返回公式表达式、每个符号的含义与单位、适用条件、判据与出处。"
        "在做任何工程计算之前必须先调用本工具看清公式，禁止凭记忆写公式或直接报数。"
        "返回的 formula_id 用于后续 solve_formula。"
    ),
)
async def search_formula(ctx: ToolContext, args: SearchFormulaArgs) -> dict:
    if args.formula_id:
        card = formula_lib.get_formula(args.formula_id)
        return {
            "status": "ok",
            "formula": card.render_for_model(),
            "formula_id": card.id,
            "required_inputs": card.required_inputs(),
            "outputs": card.outputs(),
            "is_check": card.is_check,
        }

    cards = formula_lib.search_formulas(args.query, args.category)
    if not cards:
        return {
            "status": "not_found",
            "message": (
                f"公式库中没有匹配 '{args.query}' 的公式。"
                "若确实是公式库未覆盖的非标计算，请改用 run_calculation 在沙箱中计算，"
                "并在 source 参数中说明依据来源。"
            ),
            "available_categories": formula_lib.categories(),
        }

    return {
        "status": "ok",
        "count": len(cards),
        "formulas": [
            {
                "formula_id": c.id,
                "name": c.name,
                "category": c.category,
                "expression": c.expression,
                "source": c.source,
                "required_inputs": c.required_inputs(),
                "outputs": c.outputs(),
                "is_check": c.is_check,
                "notes": c.notes,
            }
            for c in cards
        ],
        "hint": "确定用哪条后，可用 formula_id 再调本工具取完整符号定义，再 solve_formula",
    }


class LookupMaterialArgs(BaseModel):
    grade: str = Field(default="", description="材料牌号，如 45、40Cr、20CrMnTi、HT200")
    heat_treatment: str = Field(
        default="", description="热处理状态：正火 / 调质 / 渗碳淬火 / 铸态"
    )
    query: str = Field(
        default="", description="按用途检索，如 '小齿轮'、'传动轴'、'箱体'"
    )


@register(
    "lookup_material",
    layer=ToolLayer.KNOWLEDGE,
    args_model=LookupMaterialArgs,
    description=(
        "查询材料力学性能：抗拉/屈服强度、接触与弯曲疲劳极限、许用弯曲应力、"
        "弹性模量、轴径初估系数 A0 等，并返回国标号。"
        "任何用到材料性能的计算都必须先查本工具，禁止凭记忆使用 σHlim / σFlim 等数据。"
    ),
)
async def lookup_material(ctx: ToolContext, args: LookupMaterialArgs) -> dict:
    matches = loader.find_materials(
        grade=args.grade, heat_treatment=args.heat_treatment, query=args.query
    )
    if not matches:
        return {
            "status": "not_found",
            "message": "材料库中没有匹配项",
            "available": [
                {"id": m["id"], "name": m.get("name", "")}
                for m in loader.load_materials().values()
            ],
        }
    return {
        "status": "ok",
        "count": len(matches),
        "materials": [
            {
                "material_id": m["id"],
                "grade": m.get("grade", ""),
                "name": m.get("name", ""),
                "standard": m.get("standard", ""),
                "heat_treatment": m.get("heat_treatment", ""),
                "hardness": m.get("hardness", ""),
                "properties": m.get("properties", {}),
                "applications": m.get("applications", []),
                "notes": m.get("notes", ""),
            }
            for m in matches
        ],
        "hint": "落账时 basis 请填写返回的 standard 字段（如 GB/T 699-2015）",
    }


class LookupSeriesArgs(BaseModel):
    series_id: str = Field(
        description=(
            "标准系列 ID：gb1357_modulus(齿轮模数) / gb2822_diameters(标准直径) / "
            "bearing_bore_diameters(轴承内径) / center_distance_preferred(中心距) / "
            "metric_thread_coarse(螺纹) / gear_face_width_round(齿宽)"
        )
    )
    value: float = Field(description="待圆整的计算原值")
    direction: str = Field(
        default="",
        description="圆整方向：up 向上取(默认，保证安全) / down 向下取 / nearest 取最近",
    )


@register(
    "lookup_standard_series",
    layer=ToolLayer.KNOWLEDGE,
    args_model=LookupSeriesArgs,
    description=(
        "把设计计算的原始值圆整到国家标准系列，返回标准值、所属系列与国标号。"
        "设计计算结果几乎从不能直接使用——模数、轴径、中心距、齿宽、螺纹直径都必须"
        "经本工具圆整。禁止自行判断'最近的标准值是多少'。"
        "圆整后原有校核结论可能失效，必须回代重新校核。"
    ),
)
async def lookup_standard_series(ctx: ToolContext, args: LookupSeriesArgs) -> dict:
    result = loader.round_to_series(args.series_id, args.value, args.direction)
    changed_percent = (
        abs(result["rounded_value"] - result["raw_value"]) / abs(result["raw_value"]) * 100
        if result["raw_value"]
        else 0.0
    )
    out = {
        "status": "ok",
        **result,
        "change_percent": round(changed_percent, 2),
        "reminder": (
            "圆整后请回代校核：圆整改变了原计算的输入，先前的校核结论需要重新确认"
        ),
    }
    if result["out_of_range"]:
        out["warning"] = (
            f"原值 {result['raw_value']} 超出系列 {args.series_id} 的覆盖范围，"
            "已取端点值，请人工确认是否合理"
        )
    return out


class LookupPartArgs(BaseModel):
    family_id: str = Field(
        description=(
            "标准件族：key(普通平键 GB/T 1096) / "
            "bearing_deep_groove(深沟球轴承 GB/T 276) / "
            "bearing_tapered_roller(圆锥滚子轴承 GB/T 297) / "
            "hex_bolt(六角螺栓) / locating_dowel(定位销) / "
            "shaft_retaining_nut(轴端锁紧件) / shaft_seal(骨架油封) / "
            "oil_filler_breather(通气器) / oil_drain_plug(放油螺塞) / "
            "oil_level_indicator(油标) / flexible_coupling(弹性联轴器)"
        )
    )
    shaft_diameter: float | None = Field(
        default=None, description="轴径 mm。键按轴径区间选截面，轴承按内径匹配"
    )
    min_dynamic_load: float | None = Field(
        default=None, description="要求的最小基本额定动载荷 Cr (N)，仅轴承适用"
    )
    belt_type: str = Field(
        default="", description="V 带带型，如 O / A / B / C；仅 v_belt 族适用"
    )


@register(
    "lookup_standard_part",
    layer=ToolLayer.KNOWLEDGE,
    args_model=LookupPartArgs,
    description=(
        "按轴径与承载要求选取标准件，返回规格尺寸与承载参数（键的 b×h、"
        "轴承的代号/Cr/C0r/极限转速等）及国标号。"
        "选定后仍须用对应公式做强度或寿命校核，不能只凭规格表就认为满足。"
    ),
)
async def lookup_standard_part(ctx: ToolContext, args: LookupPartArgs) -> dict:
    result = loader.select_part(
        args.family_id,
        shaft_diameter=args.shaft_diameter,
        min_dynamic_load=args.min_dynamic_load,
        belt_type=args.belt_type,
    )
    if not result["candidates"]:
        raise ToolRefusal(
            f"标准件族 {args.family_id} 中没有满足条件的规格",
            remedy=(
                "请放宽条件后重试：轴径可能超出该族覆盖范围，"
                "或要求的额定动载荷过高需改用更大尺寸系列/滚子轴承"
            ),
            details={"family": result["family_name"], "standard": result["standard"]},
        )
    return {
        "status": "ok",
        **result,
        "hint": "落账时 basis 请填写返回的 standard 字段，并说明选型理由",
    }


class ListFamiliesArgs(BaseModel):
    pass


@register(
    "list_design_families",
    layer=ToolLayer.KNOWLEDGE,
    args_model=ListFamiliesArgs,
    description=(
        "列出系统支持的零件族及其设计任务书模板。开始一项新设计前调用，"
        "用于确认当前需求属于哪个已支持的零件族。"
    ),
)
async def list_design_families(ctx: ToolContext, args: ListFamiliesArgs) -> dict:
    return {
        "status": "ok",
        "families": loader.available_families(),
        "formula_categories": formula_lib.categories(),
        "hint": "确定零件族后用 start_design 建立设计任务书",
    }
