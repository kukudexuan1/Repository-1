"""表达层与校核层工具：图纸解析、建模契约、建模、仿真、校核受理。"""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import datetime, timezone
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.model_config import vision_slot
from app.schemas.common import Deliverable
from app.schemas.design_stage import DesignScope, DesignStage, Gate, SessionMode
from app.schemas.modeling_contract import (
    BodySegment,
    CoordinateSystem,
    LocalFeature,
    ModelingContract,
    UnitConversionTable,
    UnitEntry,
)
from app.services.modeling.compiler import compile_contract
from app.services.modeling.contract_validator import validate_contract
from app.schemas.session_state import ActiveAgent, PartBuild, PartBuildStatus
from app.schemas.simulation_report import (
    SimulationReport,
    SimulationResultItem,
    SimulationStatus,
)
from app.services.compute import ledger as ledger_svc

from ..prompt import build_drawing_analysis_prompt
from ..qwen_client import QwenClient, StreamEvent, StreamEventType
from .registry import ToolContext, ToolLayer, ToolRefusal, hard_gate_enabled, register

# ---------------------------------------------------------------------------
# 图纸解析
# ---------------------------------------------------------------------------


class AnalyzeDrawingArgs(BaseModel):
    focus_areas: list[str] = Field(
        default_factory=list,
        description="重点关注区域，如 '尺寸标注'、'装配关系'、'技术要求'、'公差配合'",
    )


@register(
    "analyze_drawing",
    layer=ToolLayer.EXPRESSION,
    args_model=AnalyzeDrawingArgs,
    description=(
        "解析用户上传的工程图纸，提取尺寸、结构、约束与技术要求（尺寸以 mm 记录）。"
        "在正向设计中，图纸信息属于设计输入的一个来源，解析后应用 update_design_spec "
        "记录到设计任务书；在逆向建模中，图纸尺寸可作为 from_drawing 来源直接落账。"
    ),
)
async def analyze_drawing(ctx: ToolContext, args: AnalyzeDrawingArgs) -> dict:
    uris = [a.uri for a in ctx.session.drawing_artifacts]
    if not uris:
        raise ToolRefusal(
            "当前会话没有已上传的图纸文件",
            remedy="请让用户先上传图纸，或改用对话方式提供设计输入",
        )

    vision_client = QwenClient.from_slot(vision_slot())

    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": _to_data_url(uri)}} for uri in uris
    ]
    content.append({"type": "text", "text": build_drawing_analysis_prompt(args.focus_areas)})

    def _on_event(event: StreamEvent) -> None:
        if event.type == StreamEventType.TEXT_DELTA:
            ctx.say(event.data, "sketch_parser")

    response = await vision_client.chat_stream_collect(
        messages=[{"role": "user", "content": content}],
        enable_thinking=False,
        on_event=_on_event,
    )

    text = response.content or ""
    try:
        result = _extract_json(text)
    except Exception:  # noqa: BLE001
        result = {"semantic_summary": text, "parse_error": "无法解析为 JSON"}

    ctx.session.semantic_facts["drawing"] = result
    result.setdefault("status", "ok")
    result["reminder"] = (
        "请把图纸中的设计条件用 update_design_spec 记入设计任务书；"
        "若为逆向建模，尺寸落账时 source 用 from_drawing 并在 basis 中标注图号"
    )
    return result


# ---------------------------------------------------------------------------
# 建模契约
# ---------------------------------------------------------------------------


class SegmentArg(BaseModel):
    name: str = Field(description="语义名，如 left_journal / gear_seat")
    shape: str = Field(description="cylinder / box / cone / custom")
    axis_start_cm: float
    axis_end_cm: float
    diameter_cm: float | None = None
    diameter_end_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    from_parameters: list[str] = Field(
        default_factory=list,
        description=(
            "本段尺寸引用的台账参数符号，如 ['d_shaft_1','L_journal']。"
            "系统会校验这些参数在台账中已确认，是几何尺寸溯源的依据"
        ),
    )


class FeatureArg(BaseModel):
    name: str
    feature_type: str = Field(
        description="keyway / hole / groove / chamfer / fillet / thread / boss / slot / notch / custom"
    )
    target_segment: str
    anchor_global_cm: list[float] = Field(description="特征语义锚点的全局坐标，单位 cm")
    axis_start_cm: float
    axis_end_cm: float
    dimensions_cm: dict[str, float]
    axis_centered: bool | None = None
    angular_position: str | None = None
    topology_effect: str | None = None
    verification: dict | None = None
    from_parameters: list[str] = Field(
        default_factory=list, description="本特征尺寸引用的台账参数符号"
    )


class ContractArgs(BaseModel):
    part_name: str
    part_type: str = Field(
        description="shaft / plate / housing / bracket / gear / flange / custom"
    )
    placement_policy: str = Field(
        default="absolute",
        description="absolute=严格匹配全局位置；relative=只允许整体平移",
    )
    coordinate_system: dict = Field(
        description="全局坐标系：axis(主轴 X/Y/Z)、origin(原点语义)、origin_coords、radial_up、radial_side、notes"
    )
    body_segments: list[SegmentArg] = Field(description="主体段列表，按主轴顺序排列")
    local_features: list[FeatureArg] = Field(default_factory=list)
    unit_table: list[dict] = Field(
        default_factory=list, description="mm→cm 换算表，每项含 label / mm / cm"
    )
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


@register(
    "plan_modeling_contract",
    layer=ToolLayer.EXPRESSION,
    args_model=ContractArgs,
    description=(
        "生成建模契约：全局坐标系、放置策略、主体段目标范围与局部特征全局锚点，"
        "作为目标几何的唯一权威来源，不规定 CAD 工具或草图步骤。\n"
        "前置条件：正向设计模式下参数台账必须已冻结（Gate 2）。"
        "每个段与特征的 from_parameters 必须列出其尺寸引用的台账参数符号，"
        "系统会校验这些参数存在且已确认——凭空填写的几何尺寸会被拒绝。"
    ),
)
async def plan_modeling_contract(ctx: ToolContext, args: ContractArgs) -> dict:
    session = ctx.session

    if (
        hard_gate_enabled(ctx)
        and session.mode == SessionMode.DESIGN
        and not session.gate_passed(Gate.PARAMETERS_FROZEN)
    ):
        raise ToolRefusal(
            "参数台账尚未冻结，不能进入几何表达阶段",
            remedy=(
                "请先完成全部设计计算与校核，向用户呈现参数台账并取得冻结授权后调用 "
                "freeze_parameters"
            ),
            details={"ledger_counts": session.ledger.counts()},
        )

    if session.is_assembly_scope and session.part_builds:
        if session.find_part(args.part_name) is None:
            raise ToolRefusal(
                f"零件 '{args.part_name}' 不在装配体零件清单中",
                remedy=(
                    "装配体的每份契约都必须对应清单中的一个零件。"
                    "请用清单中的零件名，或先用 declare_assembly_parts 补登记该零件"
                ),
                details={"declared_parts": [p.part_name for p in session.part_builds]},
            )

    traced, untraced = _verify_traceability(ctx, args)
    if untraced and session.mode == SessionMode.DESIGN:
        raise ToolRefusal(
            f"以下段/特征没有声明尺寸来源：{untraced}",
            remedy=(
                "请为每个段与局部特征填写 from_parameters，列出其尺寸引用的台账参数符号。"
                "几何尺寸必须能追溯到已确认的设计参数"
            ),
        )

    try:
        contract = ModelingContract(
            session_id=str(session.session_id),
            part_name=args.part_name,
            part_type=args.part_type,
            placement_policy=args.placement_policy,
            coordinate_system=CoordinateSystem(
                axis=args.coordinate_system.get("axis", "X"),
                origin=args.coordinate_system.get("origin", "origin"),
                origin_coords=args.coordinate_system.get("origin_coords", [0.0, 0.0, 0.0]),
                radial_up=args.coordinate_system.get("radial_up", "+Z"),
                radial_side=args.coordinate_system.get("radial_side", "+Y"),
                notes=args.coordinate_system.get("notes", ""),
            ),
            body_segments=[
                BodySegment(
                    **{
                        k: v
                        for k, v in seg.model_dump().items()
                        if v is not None and k != "from_parameters"
                    }
                )
                for seg in args.body_segments
            ],
            local_features=[
                LocalFeature(
                    **{
                        k: v
                        for k, v in feat.model_dump().items()
                        if v is not None and k != "from_parameters"
                    }
                )
                for feat in args.local_features
            ],
            unit_table=UnitConversionTable(
                entries=[UnitEntry(**e) for e in args.unit_table]
            ),
            assumptions=args.assumptions,
            open_questions=args.open_questions,
        )
    except Exception as exc:  # noqa: BLE001
        raise ToolRefusal(f"契约字段非法: {exc}") from exc

    validation = validate_contract(contract)
    session.contract_validation_report = validation
    if not validation.valid:
        raise ToolRefusal(
            "建模契约空间不变量校验失败",
            remedy="修正错误字段后重新生成契约，禁止猜测冲突坐标",
            details={"issues": [i.model_dump(mode="json") for i in validation.issues]},
        )
    plan = compile_contract(contract)
    session.modeling_contract = contract
    if session.modeling_plan is None:
        session.modeling_plan = compile_contract(session.modeling_contract)
    session.geometry_verification_report = None
    session.geometry_file = ""
    session.geometry_file_hash = ""
    session.design_stage = DesignStage.GEOMETRY
    session.modeling_plan = plan
    plan_path = _persist_modeling_plan(session, plan)
    contract_path = _persist_contract(session, contract)

    part = session.find_part(contract.part_name) if session.is_assembly_scope else None
    if part is not None:
        part.contract_file = contract_path
        part.part_type = contract.part_type or part.part_type
        if part.status == PartBuildStatus.PLANNED:
            part.status = PartBuildStatus.CONTRACTED
        part.updated_at = datetime.now(timezone.utc)

    out = {
        "status": "ok",
        "message": "建模契约已生成",
        "contract_summary": contract.render_for_prompt(),
        "contract_file": contract_path,
        "modeling_plan_file": plan_path,
        "contract_hash": plan.contract_hash,
        "segments_count": len(contract.body_segments),
        "features_count": len(contract.local_features),
        "traced_parameters": traced,
        "scope": session.design_scope.value,
    }
    if session.is_assembly_scope:
        out["assembly_progress"] = _part_progress(session)
    if contract.open_questions:
        out["status"] = "needs_clarification"
        out["message"] = "契约已生成但存在未确认问题，请先向用户澄清再建模"
        out["open_questions"] = contract.open_questions
    else:
        out["next"] = "可以调用 build_model 开始建模"
    return out


def _verify_traceability(ctx: ToolContext, args: ContractArgs) -> tuple[list[str], list[str]]:
    traced: list[str] = []
    untraced: list[str] = []

    for item in list(args.body_segments) + list(args.local_features):
        refs = item.from_parameters
        if not refs:
            untraced.append(item.name)
            continue
        for symbol in refs:
            try:
                ledger_svc.resolve_for_geometry(ctx.session, symbol)
            except ledger_svc.LedgerError as exc:
                raise ToolRefusal(
                    f"段/特征 '{item.name}' 引用的参数有问题：{exc}"
                ) from exc
            traced.append(f"{item.name}←{symbol}")
    return traced, untraced


def _part_progress(session) -> dict:
    """装配体逐件建模进度，供工具返回值与提示词共用。"""
    built = session.built_parts()
    unbuilt = session.unbuilt_parts()
    return {
        "total": len(session.part_builds),
        "built": len(built),
        "built_parts": [
            {"part_name": p.part_name, "geometry_file": p.geometry_file} for p in built
        ],
        "remaining_parts": [
            {"part_name": p.part_name, "role": p.role, "status": p.status.value}
            for p in unbuilt
        ],
        "all_built": session.all_parts_built(),
    }


def _slugify_part(name: str) -> str:
    """把零件名转成可安全用于文件名的短标识。"""
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", name.strip())
    return cleaned.strip("_")[:40] or "part"


def _part_file_suffix(session, part_name: str) -> str:
    """装配体范围下按零件名区分产物文件，避免逐件建模时相互覆盖。"""
    if not session.is_assembly_scope:
        return ""
    return f"_{_slugify_part(part_name)}"


def _persist_contract(session, contract: ModelingContract) -> str:
    export_dir = os.getenv("MCPCAD_EXPORT_DIR", "D:/Inventor_Export")
    suffix = _part_file_suffix(session, contract.part_name)
    path = f"{export_dir.rstrip('/')}/session_{session.session_id}{suffix}_contract.json"
    try:
        os.makedirs(export_dir, exist_ok=True)
        Path(path).write_text(
            json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        session.modeling_contract_file = path
        return path
    except Exception as exc:  # noqa: BLE001
        return f"(写入失败: {exc})"


# ---------------------------------------------------------------------------
# 建模
# ---------------------------------------------------------------------------


def _persist_modeling_plan(session, plan) -> str:
    export_dir = os.getenv("MCPCAD_EXPORT_DIR", "D:/Inventor_Export")
    suffix = _part_file_suffix(session, getattr(plan, "part_name", ""))
    path = f"{export_dir.rstrip('/')}/session_{session.session_id}{suffix}_plan.json"
    try:
        os.makedirs(export_dir, exist_ok=True)
        Path(path).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        session.modeling_plan_file = path
        return path
    except Exception as exc:  # noqa: BLE001
        return f"(写入失败: {exc})"


class BuildModelArgs(BaseModel):
    execution_intent: str = Field(
        description="整体建模意图的自然语言描述（要建什么、关键约束），不要写分步工具指令"
    )
    stay_in_modeling: bool = Field(
        default=False,
        description=(
            "是否在建模完成后停留在建模子 Agent 中继续调试几何。"
            "默认 false——控制权立即交还你（主设计模型）。"
            "仅当用户明确要求反复调整几何细节时才设为 true"
        ),
    )


@register(
    "build_model",
    layer=ToolLayer.EXPRESSION,
    args_model=BuildModelArgs,
    description=(
        "在 Autodesk Inventor 中创建三维参数化模型并导出 STEP。"
        "内部由建模子 Agent 自主规划并调用 mcp-cad 工具，你只需给出建模意图——"
        "不要在意图中讨论草图平面、工作轴或单位换算，那是子 Agent 的职责。"
        "前置条件：必须已调用 plan_modeling_contract 生成契约。"
    ),
)
async def build_model(ctx: ToolContext, args: BuildModelArgs) -> dict:
    session = ctx.session
    if session.modeling_contract is None:
        raise ToolRefusal(
            "尚未生成建模契约，无法建模",
            remedy="请先调用 plan_modeling_contract 生成契约",
            details={"error_code": "missing_modeling_contract"},
        )

    from ..modeling_agent import ModelingAgent, ModelingResult

    def _stream(event: StreamEvent) -> None:
        if event.type in (StreamEventType.TEXT_DELTA, StreamEventType.THINKING_DELTA):
            ctx.say(event.data, "modeling")

    if session.modeling_plan is None:
        session.modeling_plan = compile_contract(session.modeling_contract)
    session.geometry_verification_report = None
    session.geometry_file = ""
    session.geometry_file_hash = ""
    session.design_stage = DesignStage.GEOMETRY
    agent: ModelingAgent = ctx.extras.get("modeling_agent") or ModelingAgent()

    try:
        result = await agent.build(
            execution_intent=args.execution_intent,
            session_id=str(session.session_id),
            stream_callback=_stream,
            prior_messages=session.modeling_messages or None,
            contract=session.modeling_contract,
            plan=session.modeling_plan,
        )
    except Exception as exc:  # noqa: BLE001 - 保留子 agent 已积累的上下文
        result = ModelingResult(
            success=False,
            error=f"建模子 agent 异常: {exc}",
            messages=session.modeling_messages or [],
        )

    return apply_modeling_result(session, result, stay=args.stay_in_modeling)


def apply_modeling_result(session, result, *, stay: bool = False) -> dict:
    """落地建模结果。sticky 默认关闭，控制权交还主设计模型。"""
    session.modeling_messages = result.messages
    if result.verification_report:
        from app.schemas.modeling_plan import GeometryVerificationReport
        session.geometry_verification_report = GeometryVerificationReport.model_validate(result.verification_report)
    session.active_agent = ActiveAgent.MODELING if stay else ActiveAgent.NONE

    if result.success and result.geometry_file:
        session.geometry_file = result.geometry_file
        try:
            from app.services.modeling.verifier import file_sha256
            session.geometry_file_hash = file_sha256(result.geometry_file)
            if session.geometry_verification_report:
                session.geometry_verification_report.geometry_hash = session.geometry_file_hash
                session.geometry_verification_report.stale = False
        except OSError:
            session.geometry_file_hash = ""
        part_name = (
            session.modeling_contract.part_name if session.modeling_contract else "零件"
        )
        # 装配体逐件建模时按零件名保留各自的几何交付物，避免后一个零件挤掉前一个；
        # 单零件范围下重建则替换旧条目
        if session.is_assembly_scope:
            def _keep(d) -> bool:
                return d.kind != "geometry" or (
                    d.path != result.geometry_file
                    and not d.title.startswith(f"{part_name} ")
                )
        else:
            def _keep(d) -> bool:
                return d.kind != "geometry"

        session.deliverables = [d for d in session.deliverables if _keep(d)] + [
            Deliverable(
                kind="geometry",
                title=f"{part_name} STEP 几何",
                path=result.geometry_file,
            )
        ]
        session.semantic_facts["last_model_build"] = {
            "status": "success",
            "geometry_file": result.geometry_file,
            "iterations": result.iterations,
            "part_name": part_name,
        }

        out = {
            "status": "success",
            "message": f"建模完成，共 {result.iterations} 轮",
            "geometry_file": result.geometry_file,
            "feature_tree": result.feature_tree,
            "control_returned": not stay,
            "scope": session.design_scope.value,
        }

        if not session.is_assembly_scope:
            out["next"] = (
                "请核对几何与台账是否一致，然后进入校核验证阶段做零件级仿真"
            )
            return out

        part = session.find_part(part_name)
        if part is not None:
            part.status = PartBuildStatus.BUILT
            part.geometry_file = result.geometry_file
            part.geometry_hash = session.geometry_file_hash
            part.updated_at = datetime.now(timezone.utc)

        progress = _part_progress(session)
        out["assembly_progress"] = progress

        if part is None and session.part_builds:
            out["warning"] = (
                f"零件 '{part_name}' 不在零件清单中，进度未计入。"
                "请确认契约的 part_name 与 declare_assembly_parts 登记的名称一致"
            )

        if progress["all_built"]:
            session.design_stage = DesignStage.ASSEMBLY_HANDOFF
            out["next"] = (
                f"全部 {progress['total']} 个零件已建模完成。"
                "系统不具备可靠的自动装配能力，装配须由用户手工完成。"
                "请勿询问用户是否进入仿真，而是要求用户："
                "① 在 Inventor 中新建装配体，把这些零件按设计意图装配好；"
                "② 保存为 .iam；"
                "③ 把 .iam 路径发给你（系统会打开并导出为 STP），"
                "或用户自行导出 STP 后直接提交 .stp 路径。"
                "拿到路径后调用 submit_assembly_geometry，再进入装配级仿真。"
            )
            out["attention"] = (
                "禁止用单个零件的几何冒充装配体去跑装配级仿真"
            )
        else:
            remaining = [p["part_name"] for p in progress["remaining_parts"]]
            out["next"] = (
                f"还有 {len(remaining)} 个零件待建模：{remaining}。"
                "请继续对下一个零件 plan_modeling_contract + build_model。"
                "全部建完后再要求用户手工装配，此时不要进入仿真"
            )
        return out

    session.last_error = result.error or "建模失败"
    return {
        "status": "failure",
        "message": result.error or "建模失败",
        "error": result.error,
        "tool_calls": result.tool_calls,
        "control_returned": not stay,
        "reminder": "不要为了建模方便而修改已冻结的设计参数",
    }


class SetModelingStatusArgs(BaseModel):
    status: str = Field(description="建模/几何验证状态：pass / fail / indeterminate")
    reason: str = Field(
        description="作为主设计模型直接判定该状态的依据，将记入审计轨迹"
    )
    geometry_file: str = Field(
        default="",
        description="可选：要登记为会话几何的 STEP 绝对路径，留空则沿用现有几何",
    )


@register(
    "set_modeling_status",
    layer=ToolLayer.EXPRESSION,
    args_model=SetModelingStatusArgs,
    description=(
        "由主设计模型直接判定并写入建模/几何验证状态，不必等待建模子 Agent 标记完成。"
        "用于你已依据子 Agent 证据、用户确认或已有几何自行得出结论的场景。"
        "写入的报告会标记为 main_model 来源并记录你的判定依据；"
        "status=pass 会解除对下游仿真的几何门控。"
    ),
)
async def set_modeling_status(ctx: ToolContext, args: SetModelingStatusArgs) -> dict:
    from app.schemas.modeling_plan import (
        GeometryVerificationReport,
        ReportSource,
        VerificationStatus,
    )

    session = ctx.session
    if not args.reason.strip():
        raise ToolRefusal("需要记录你判定该建模状态的依据")
    try:
        status = VerificationStatus(args.status.strip().lower())
    except ValueError as exc:
        raise ToolRefusal(
            f"未知状态: {args.status}",
            remedy="status 取 pass / fail / indeterminate",
        ) from exc

    geometry_file = args.geometry_file.strip() or session.geometry_file
    if geometry_file:
        if not Path(geometry_file).is_file():
            raise ToolRefusal(
                f"几何文件不存在或不可访问: {geometry_file}",
                remedy="请检查路径，或留空以沿用现有会话几何",
            )
        session.geometry_file = geometry_file

    geometry_hash = ""
    if geometry_file:
        try:
            from app.services.modeling.verifier import file_sha256

            geometry_hash = file_sha256(geometry_file)
        except OSError:
            geometry_hash = ""
    session.geometry_file_hash = geometry_hash

    contract_hash = ""
    if session.modeling_plan is not None:
        contract_hash = session.modeling_plan.contract_hash

    session.geometry_verification_report = GeometryVerificationReport(
        status=status,
        contract_hash=contract_hash,
        geometry_hash=geometry_hash,
        stale=False,
        source=ReportSource.MAIN_MODEL,
        override_reason=args.reason.strip(),
    )
    session.design_stage = DesignStage.GEOMETRY
    session.semantic_facts["modeling_status_override"] = {
        "status": status.value,
        "reason": args.reason.strip(),
        "geometry_file": geometry_file,
    }

    return {
        "status": "ok",
        "message": f"建模状态已由主设计模型置为 {status.value}",
        "geometry_file": geometry_file,
        "geometry_verified": status.value == "pass",
        "source": "main_model",
        "next": (
            "可以进入校核验证阶段运行仿真"
            if status.value == "pass"
            else "几何未判定为通过，请先修复建模问题"
        ),
    }


# ---------------------------------------------------------------------------
# 装配交接：用户手工装配后提交装配体几何
# ---------------------------------------------------------------------------

_STEP_SUFFIXES = {".stp", ".step"}
_ASSEMBLY_SUFFIXES = {".iam"}


class SubmitAssemblyArgs(BaseModel):
    path: str = Field(
        description=(
            "用户提交的装配体文件绝对路径。"
            "支持 .iam（系统会用 mcp-cad 打开并导出为 STP）"
            "或 .stp/.step（用户已自行导出，直接使用）"
        )
    )
    user_statement: str = Field(
        description="用户确认装配已完成的原话，作为装配交接的记录"
    )
    notes: list[str] = Field(
        default_factory=list,
        description="用户在装配时说明的偏差或注意事项，如替换了某个标准件、简化了某处结构",
    )


@register(
    "submit_assembly_geometry",
    layer=ToolLayer.EXPRESSION,
    args_model=SubmitAssemblyArgs,
    description=(
        "接收用户手工装配完成的装配体文件，作为装配级仿真的几何输入，并通过装配交接关口。"
        "仅装配体范围可用。\n"
        "当前 mcp-cad 的装配工具链不足以可靠地自动装配（缺 occurrence 面/边枚举、"
        "放置无姿态参数、无干涉与自由度检查），因此装配这一步由用户在 Inventor 中手工完成。\n"
        "两种提交方式：\n"
        "  · 用户提交 .iam —— 系统调用 mcp-cad 打开该装配体并导出为 STP 后使用；\n"
        "  · 用户提交 .stp/.step —— 用户已自行导出，直接使用。\n"
        "通过后才允许对装配体运行 run_simulation。"
    ),
)
async def submit_assembly_geometry(ctx: ToolContext, args: SubmitAssemblyArgs) -> dict:
    session = ctx.session

    if not session.is_assembly_scope:
        raise ToolRefusal(
            f"当前设计范围是 {session.design_scope.value}，无需装配交接",
            remedy=(
                "单个零件的几何由 build_model 直接产出，可直接 run_simulation。"
                "若本项设计确实是装配体，请先 set_design_scope(scope=assembly)"
            ),
        )
    if not args.user_statement.strip():
        raise ToolRefusal(
            "缺少用户确认装配完成的表述",
            remedy="装配交接需要记录用户的明示确认，不得代为断言装配已完成",
        )

    raw = args.path.strip().strip('"').strip("'")
    if not raw:
        raise ToolRefusal("路径为空", remedy="请让用户提供装配体文件的绝对路径")

    source = Path(raw)
    if not source.is_file():
        raise ToolRefusal(
            f"文件不存在或不可访问: {source}",
            remedy="请让用户确认路径无误、文件已保存且未被占用",
        )

    suffix = source.suffix.lower()
    if suffix in _STEP_SUFFIXES:
        step_path = str(source)
        source_kind = "stp"
        export_note = "用户直接提交 STEP，未经系统转换"
    elif suffix in _ASSEMBLY_SUFFIXES:
        step_path, export_note = await _export_assembly_step(source, session)
        source_kind = "iam"
    else:
        raise ToolRefusal(
            f"不支持的文件类型: {suffix or '(无扩展名)'}",
            remedy="请提交 .iam 装配体文件，或已导出的 .stp/.step 文件",
        )

    from app.services.modeling.verifier import file_sha256

    try:
        step_hash = file_sha256(step_path)
    except OSError as exc:
        raise ToolRefusal(f"无法读取装配体 STEP: {exc}") from exc

    unbuilt = [p.part_name for p in session.unbuilt_parts()]
    handoff = session.assembly_handoff
    handoff.submitted = True
    handoff.source_kind = source_kind
    handoff.iam_file = str(source) if source_kind == "iam" else ""
    handoff.step_file = step_path
    handoff.step_hash = step_hash
    handoff.user_statement = args.user_statement
    handoff.part_count = len(session.built_parts())
    handoff.notes = list(args.notes)
    handoff.submitted_at = datetime.now(timezone.utc).isoformat()

    session.approve_gate(
        Gate.ASSEMBLY_SUBMITTED,
        statement=args.user_statement,
        conditions=list(args.notes),
    )
    session.design_stage = DesignStage.VERIFICATION
    session.deliverables = [
        d for d in session.deliverables if d.kind != "assembly_geometry"
    ] + [
        Deliverable(
            kind="assembly_geometry",
            title="装配体 STEP 几何（用户手工装配）",
            path=step_path,
            notes=export_note,
        )
    ]

    ctx.say(f"[装配交接] 已接收装配体几何：{step_path}\n")

    out = {
        "status": "ok",
        "gate": Gate.ASSEMBLY_SUBMITTED.value,
        "stage": session.design_stage.value,
        "source_kind": source_kind,
        "source_file": str(source),
        "step_file": step_path,
        "export_note": export_note,
        "parts_built": len(session.built_parts()),
        "user_notes": args.notes,
        "next": (
            "可以对装配体运行 run_simulation 做装配级仿真。"
            "载荷取自台账，判据取自设计任务书；"
            "装配级分析应关注零件间的接触、传力路径与整体变形"
        ),
    }
    if unbuilt:
        out["warning"] = (
            f"零件清单中仍有 {len(unbuilt)} 个零件未标记为已建模：{unbuilt}。"
            "若用户的装配体已包含这些零件（例如用户自行补建），可以继续；"
            "否则请向用户确认装配体是否完整"
        )
    if args.notes:
        out["attention"] = (
            "用户说明的装配偏差已记入交接记录，若影响承载或几何应在设计说明书中如实反映"
        )
    return out


async def _export_assembly_step(source: Path, session) -> tuple[str, str]:
    """用 mcp-cad 打开用户的 .iam 并导出为 STP。"""
    from app.mcp import MCPCAD, get_manager

    manager = get_manager()
    if not manager.is_connected(MCPCAD):
        raise ToolRefusal(
            "mcp-cad 未连接，无法打开 .iam 并导出 STP",
            remedy=(
                "请启动 Inventor 与 mcp-cad 后重试，"
                "或让用户在 Inventor 中自行导出 STP 并提交 .stp 路径"
            ),
        )

    opened = await manager.call(MCPCAD, "doc_open", {"path": str(source)})
    if not opened.success:
        raise ToolRefusal(
            f"打开装配体失败: {opened.error}",
            remedy=(
                "请确认该 .iam 及其引用的零件文件都可访问、未被占用；"
                "也可让用户自行导出 STP 后提交 .stp 路径"
            ),
        )

    export_dir = os.getenv("MCPCAD_EXPORT_DIR", "D:/Inventor_Export")
    step_path = (
        f"{export_dir.rstrip('/')}/session_{session.session_id}_assembly.stp"
    )
    try:
        os.makedirs(export_dir, exist_ok=True)
    except OSError as exc:
        raise ToolRefusal(f"无法创建导出目录 {export_dir}: {exc}") from exc

    exported = await manager.call(MCPCAD, "export_step", {"path": step_path})
    if not exported.success:
        raise ToolRefusal(
            f"导出装配体 STEP 失败: {exported.error}",
            remedy="请让用户在 Inventor 中手工导出 STP 并提交 .stp 路径",
        )
    if not Path(step_path).is_file():
        raise ToolRefusal(
            f"mcp-cad 报告导出成功但文件不存在: {step_path}",
            remedy="请让用户手工导出 STP 并提交 .stp 路径",
        )
    return step_path, f"由系统从 {source.name} 打开并导出"


# ---------------------------------------------------------------------------
# 仿真
# ---------------------------------------------------------------------------


def _validate_part_geometry(session, geometry_file: str) -> None:
    """零件级 CAE 前置校验：几何必须是本会话建模、验证通过且未被改动的。"""
    if geometry_file != session.geometry_file:
        raise ToolRefusal(
            "拒绝对外部或未登记几何运行 CAE",
            remedy="请先通过确定性建模、结构化验证和导出 Gate 生成会话几何",
        )
    report = session.geometry_verification_report
    if report is None or str(report.status.value) != "pass":
        raise ToolRefusal(
            "几何尚未通过结构化验证，禁止运行 CAE",
            remedy="请重新执行 build_model 并解决所有几何验证失败项",
        )
    from app.services.modeling.verifier import file_sha256

    current_hash = file_sha256(geometry_file)
    if not session.geometry_file_hash or current_hash != session.geometry_file_hash:
        report.stale = True
        raise ToolRefusal(
            "几何文件已在验证后发生变化，验证证据已失效",
            remedy="请重新建模或重新验证并导出，再运行 CAE",
        )


def _validate_assembly_geometry(session, geometry_file: str) -> None:
    """装配级 CAE 前置校验。

    装配几何由用户手工装配产出，系统无法对其做逐特征结构化验证，
    因此改为校验交接链路：装配交接关口已通过、几何就是用户提交的那份、
    且提交后未被改动。
    """
    handoff = session.assembly_handoff
    if not session.gate_passed(Gate.ASSEMBLY_SUBMITTED) or not handoff.submitted:
        unbuilt = [p.part_name for p in session.unbuilt_parts()]
        raise ToolRefusal(
            "装配体尚未交接，禁止运行装配级 CAE",
            remedy=(
                "装配体仿真必须基于真实装配几何。请先逐零件建模完毕，"
                "再要求用户在 Inventor 中手工装配并保存，"
                "然后用 submit_assembly_geometry 提交 .iam 或 .stp 路径。"
                "禁止用单个零件的几何冒充装配体"
            ),
            details={
                "parts_total": len(session.part_builds),
                "parts_built": len(session.built_parts()),
                "parts_unbuilt": unbuilt,
            },
        )
    if geometry_file != handoff.step_file:
        raise ToolRefusal(
            "拒绝对未经装配交接的几何运行装配级 CAE",
            remedy=(
                f"当前已交接的装配体几何为 {handoff.step_file}。"
                "若用户重新装配过，请让其重新提交并调用 submit_assembly_geometry"
            ),
        )

    from app.services.modeling.verifier import file_sha256

    current_hash = file_sha256(geometry_file)
    if not handoff.step_hash or current_hash != handoff.step_hash:
        raise ToolRefusal(
            "装配体几何在提交后发生了变化，交接证据已失效",
            remedy="请让用户确认最终装配状态并重新 submit_assembly_geometry",
        )


class RunSimulationArgs(BaseModel):
    analysis_intent: str = Field(
        description=(
            "仿真意图：载荷、边界条件、材料、工况。"
            "载荷数值应取自参数台账，判据取自设计任务书的安全系数"
        )
    )
    analysis_type: str = Field(
        default="",
        description=(
            "steady_state_thermal / transient_thermal / static_structural / "
            "transient_structural / modal / harmonic_response / response_spectrum / "
            "random_vibration / cfx / fluent"
        ),
    )
    geometry_file: str = Field(
        default="",
        description=(
            "STEP 几何文件绝对路径，留空则用会话中已登记的几何。"
            "装配体范围下留空即可——系统会自动取用户提交的装配体 STEP"
        ),
    )
    stay_in_analysis: bool = Field(
        default=False, description="是否停留在仿真子 Agent 中继续调试，默认 false"
    )


@register(
    "run_simulation",
    layer=ToolLayer.EXPRESSION,
    args_model=RunSimulationArgs,
    description=(
        "对已建好的三维模型运行 ANSYS Workbench 有限元校核。"
        "这是对解析校核的独立验证，不能替代设计计算——"
        "不允许跳过设计计算直接靠仿真反复试尺寸。"
        "结果应与详细计算阶段的解析校核做对比；差异超过 30% 说明解析模型假设可能不成立。\n"
        "几何来源按设计范围自动决定：单个零件用 build_model 产出的零件 STEP；"
        "装配体用 submit_assembly_geometry 交接的装配体 STEP——"
        "装配体范围下若尚未交接，本工具会直接拒绝，"
        "不允许用单个零件的几何冒充装配体做装配级仿真。"
    ),
)
async def run_simulation(ctx: ToolContext, args: RunSimulationArgs) -> dict:
    session = ctx.session
    geometry_file = args.geometry_file.strip() or session.simulation_geometry()
    if not geometry_file:
        raise ToolRefusal(
            "尚无可用几何文件",
            remedy="请先建模，或直接提供 STEP 文件的绝对路径",
        )
    if not Path(geometry_file).is_file():
        raise ToolRefusal(
            f"几何文件不存在或不可访问: {geometry_file}",
            remedy="请检查路径，或重新建模并导出 STEP",
        )

    if session.is_assembly_scope:
        _validate_assembly_geometry(session, geometry_file)
    else:
        _validate_part_geometry(session, geometry_file)

    from ..analysis_agent import AnalysisAgent

    def _stream(event: StreamEvent) -> None:
        if event.type in (StreamEventType.TEXT_DELTA, StreamEventType.THINKING_DELTA):
            ctx.say(event.data, "analysis")

    # 装配体范围下 geometry_file 是装配体 STEP，不能覆盖零件级几何字段
    if not session.is_assembly_scope:
        session.geometry_file = geometry_file
    session.design_stage = DesignStage.VERIFICATION
    agent: AnalysisAgent = ctx.extras.get("analysis_agent") or AnalysisAgent()

    result = await agent.run(
        analysis_intent=args.analysis_intent,
        geometry_file=geometry_file,
        analysis_type=args.analysis_type,
        session_id=str(session.session_id),
        stream_callback=_stream,
        prior_messages=session.analysis_messages or None,
    )
    return apply_analysis_result(session, result, geometry_file, stay=args.stay_in_analysis)


def apply_analysis_result(session, result, geometry_file: str, *, stay: bool = False) -> dict:
    session.analysis_messages = result.messages
    session.active_agent = ActiveAgent.ANALYSIS if stay else ActiveAgent.NONE

    status_map = {
        "pass": (SimulationStatus.PASS, SimulationStatus.PASS),
        "fail": (SimulationStatus.FAIL, SimulationStatus.FAIL),
    }
    status, verdict = status_map.get(
        result.status, (SimulationStatus.ERROR, SimulationStatus.NOT_RUN)
    )

    report = SimulationReport(
        geometry_file=geometry_file,
        status=status,
        pass_or_fail=verdict,
        issues=list(result.result_data.get("issues", [])),
        recommended_adjustments=list(result.result_data.get("recommended_adjustments", [])),
        raw_result=result.result_data,
    )
    for item in result.result_data.get("result_items", []) or []:
        if isinstance(item, dict):
            report.result_items.append(
                SimulationResultItem(
                    name=str(item.get("name", "")),
                    value=item.get("value"),
                    unit=str(item.get("unit", "")),
                    limit=item.get("limit"),
                    passed=bool(item.get("passed", True)),
                    detail=str(item.get("detail", "")),
                )
            )
    session.simulation_report = report
    if result.status != "pass" and result.error:
        session.last_error = result.error

    out = {
        "status": "success" if result.success else "failure",
        "pass_or_fail": result.status,
        "summary": result.summary,
        "result_items": result.result_data.get("result_items", []),
        "issues": report.issues,
        "recommended_adjustments": report.recommended_adjustments,
        "error": result.error,
        "control_returned": not stay,
    }
    if result.status == "pass":
        out["next"] = (
            "请把有限元结果与详细计算阶段的解析校核做对比，说明是否一致；"
            "确认无矛盾后调用 accept_verification 通过 Gate 3"
        )
    else:
        out["attention"] = (
            "校核不通过。请定位失效参数，用 get_calculation_record 回溯其计算依据，"
            "提出调整方案并 request_user_decision 征询后再返工。"
            "禁止修改判据或降低安全系数使结果通过"
        )
    return out


class SetSimulationStatusArgs(BaseModel):
    status: str = Field(description="仿真/校核状态：pass / fail / not_run / error")
    reason: str = Field(
        description="作为主设计模型直接判定该状态的依据，将记入审计轨迹"
    )
    summary: str = Field(default="", description="可选：对该判定的简要说明")
    geometry_file: str = Field(
        default="", description="可选：该结论对应的几何文件路径，留空则沿用会话几何"
    )


@register(
    "set_simulation_status",
    layer=ToolLayer.EXPRESSION,
    args_model=SetSimulationStatusArgs,
    description=(
        "由主设计模型直接判定并写入仿真/校核状态，不必等待仿真子 Agent 标记完成。"
        "用于你已依据子 Agent 结果、解析校核或用户确认自行得出结论的场景。"
        "写入的报告会标记为 main_model 来源并记录判定依据；"
        "status=pass 后可继续 accept_verification。"
    ),
)
async def set_simulation_status(ctx: ToolContext, args: SetSimulationStatusArgs) -> dict:
    session = ctx.session
    if not args.reason.strip():
        raise ToolRefusal("需要记录你判定该仿真状态的依据")
    try:
        status = SimulationStatus(args.status.strip().lower())
    except ValueError as exc:
        raise ToolRefusal(
            f"未知状态: {args.status}",
            remedy="status 取 pass / fail / not_run / error",
        ) from exc

    geometry_file = args.geometry_file.strip() or session.simulation_geometry()
    report = session.simulation_report or SimulationReport()
    report.geometry_file = geometry_file
    report.status = status
    report.pass_or_fail = status
    report.source = "main_model"
    report.override_reason = args.reason.strip()
    session.simulation_report = report
    session.design_stage = DesignStage.VERIFICATION
    session.semantic_facts["simulation_status_override"] = {
        "status": status.value,
        "reason": args.reason.strip(),
        "summary": args.summary,
    }

    return {
        "status": "ok",
        "message": f"仿真状态已由主设计模型置为 {status.value}",
        "pass_or_fail": status.value,
        "source": "main_model",
        "next": (
            "校核通过，可调用 accept_verification 通过 Gate 3"
            if status.value == "pass"
            else "校核未通过，请定位问题后返工"
        ),
    }


class AcceptVerificationArgs(BaseModel):
    user_statement: str = Field(description="用户接受校核结论的原话或明确表述")
    analytical_vs_fea: str = Field(
        description=(
            "解析校核与有限元结果的对比说明：量级是否一致、差异多少、"
            "若差异较大则说明原因（应力集中、边界简化等）"
        )
    )
    residual_risks: list[str] = Field(
        default_factory=list, description="遗留风险或需在制造/使用中注意的事项"
    )


@register(
    "accept_verification",
    layer=ToolLayer.EXPRESSION,
    args_model=AcceptVerificationArgs,
    description=(
        "受理校核结论，通过 Gate 3（校核验证）。通过后才允许生成设计说明书。"
        "系统会拒绝在有限元未通过或存在失效计算时受理。"
    ),
)
async def accept_verification(ctx: ToolContext, args: AcceptVerificationArgs) -> dict:
    session = ctx.session
    if hard_gate_enabled(ctx):
        report = session.simulation_report
        if report is None:
            raise ToolRefusal(
                "尚未进行有限元校核",
                remedy="请先 run_simulation 完成校核",
            )
        if report.pass_or_fail != SimulationStatus.PASS:
            raise ToolRefusal(
                f"有限元校核结论为 {report.pass_or_fail.value}，不能受理",
                remedy="请先解决校核问题：调整参数后重算、重建几何、重新仿真",
                details={"issues": report.issues},
            )
        failed = session.failed_checks()
        if failed:
            raise ToolRefusal(
                f"解析校核仍有 {len(failed)} 项未通过：{[r.title for r in failed]}",
                remedy="有限元通过不代表解析校核可以不通过，请先修正",
            )
        if not args.user_statement.strip():
            raise ToolRefusal("Gate 3 需要记录用户的明示受理表述")

    statement = args.user_statement.strip() or "E5 C2: agent self-check"
    session.approve_gate(
        Gate.VERIFICATION_ACCEPTED,
        statement=statement,
        conditions=args.residual_risks,
    )
    session.design_stage = DesignStage.DELIVERY
    session.semantic_facts["verification_comparison"] = args.analytical_vs_fea
    ctx.say("[Gate 3] 校核结论已受理\n")

    return {
        "status": "ok",
        "gate": Gate.VERIFICATION_ACCEPTED.value,
        "stage": session.design_stage.value,
        "residual_risks": args.residual_risks,
        "next": "可以调用 generate_design_report 生成设计说明书与计算书",
    }


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _to_data_url(raw_path: str) -> str:
    if raw_path.startswith(("http://", "https://", "data:")):
        return raw_path
    path = Path(raw_path)
    if not path.is_file():
        raise FileNotFoundError(f"图纸文件不存在: {path}")
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        raise RuntimeError(f"仅支持图片格式，当前: {path.suffix}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
    if fence:
        cleaned = fence.group(1).strip()
    else:
        block = re.search(r"(\{.*\})", cleaned, flags=re.S)
        if block:
            cleaned = block.group(1).strip()
    return json.loads(cleaned)
