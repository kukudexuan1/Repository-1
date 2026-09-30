"""设计交互层工具：需求收敛、方案备选、人在回路提问、阶段推进。"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.decision import DecisionKind, DecisionOption, PendingDecision
from app.schemas.design_spec import DesignSpec, SpecItem, SpecStatus
from app.schemas.design_stage import (
    SCOPE_LABELS,
    STAGE_LABELS,
    STAGE_REQUIRED_GATE,
    DesignScope,
    DesignStage,
    Gate,
    SessionMode,
)
from app.schemas.session_state import (
    AssemblyHandoff,
    PartBuild,
    PartBuildStatus,
    SchemeAlternative,
)
from app.services.knowledge import loader

from .registry import ToolContext, ToolInterrupt, ToolLayer, ToolRefusal, register


class StartDesignArgs(BaseModel):
    family: str = Field(
        description="零件族标识，由 list_design_families 获得，如 gearbox_single_stage"
    )
    title: str = Field(default="", description="本项设计的名称，如 '带式输送机用单级减速器'")
    scope: DesignScope = Field(
        default=DesignScope.UNDECIDED,
        description=(
            "设计对象范围。single_part=单个零件（一份契约、一次建模，几何完成后"
            "直接进入零件级仿真）；assembly=装配体（逐零件建模，全部建完后须由"
            "用户手工装配并提交 iam/stp，再进入装配级仿真）；"
            "undecided=暂不确定，须在设计输入收敛阶段用 set_design_scope 判定。"
            "两种范围的流程严格度完全相同，都要交付契约、设计说明书与设计计算书"
        ),
    )
    mode: SessionMode = Field(
        default=SessionMode.DESIGN,
        description=(
            "design=正向设计（从需求出发做完整设计计算）；"
            "reverse_modeling=逆向建模（已有完整图纸，尺寸取自图纸，只补校核）"
        ),
    )


@register(
    "start_design",
    layer=ToolLayer.INTERACTION,
    args_model=StartDesignArgs,
    description=(
        "按零件族模板建立设计任务书，正式开始一项设计。"
        "返回该零件族需要的全部设计输入条目及当前缺失清单。"
        "这是设计工作的第一步，在此之前不要讨论任何具体尺寸。\n"
        "系统同时支持装配体设计与单个零件设计：若用户的需求只涉及一个零件"
        "（一根轴、一块板、一个支架），且既有零件族都不匹配，"
        "请用 family=generic_part 配合 scope=single_part。"
        "无论哪种范围，都必须交付建模契约、设计说明书与设计计算书。"
    ),
)
async def start_design(ctx: ToolContext, args: StartDesignArgs) -> dict:
    try:
        template = loader.get_spec_template(args.family)
    except loader.KnowledgeError as exc:
        raise ToolRefusal(str(exc), remedy="请先调用 list_design_families 查看支持的零件族") from exc

    spec = DesignSpec(
        family=args.family,
        family_label=template.get("family_label", args.family),
        title=args.title or template.get("title", ""),
    )
    for raw in template.get("items", []) or []:
        spec.items[raw["key"]] = SpecItem(
            key=raw["key"],
            label=raw.get("label", raw["key"]),
            required=bool(raw.get("required", True)),
            group=raw.get("group", "其他"),
            needed_by_stage=raw.get("needed_by_stage", "spec_gathering"),
            hint=raw.get("hint", ""),
        )

    session = ctx.session
    session.design_spec = spec
    session.mode = args.mode
    session.design_scope = args.scope
    session.part_builds = []
    session.assembly_handoff = AssemblyHandoff()
    session.design_stage = DesignStage.SPEC_GATHERING

    missing = spec.missing_required(upto_stage=DesignStage.SPEC_GATHERING.value)
    ctx.say(f"[设计任务书] {spec.family_label}，共 {len(spec.items)} 项设计输入\n")
    return {
        "status": "ok",
        "family": spec.family,
        "family_label": spec.family_label,
        "mode": session.mode.value,
        "scope": session.design_scope.value,
        "stage": session.design_stage.value,
        "all_items": [
            {
                "key": i.key,
                "label": i.label,
                "group": i.group,
                "required": i.required,
                "needed_by_stage": i.needed_by_stage,
                "hint": i.hint,
            }
            for i in spec.items.values()
        ],
        "missing_now": [{"key": i.key, "label": i.label, "hint": i.hint} for i in missing],
        "next": "请把用户已给出的条件用 update_design_spec 记录，再就缺失项一次性提问",
        "scope_reminder": (
            "设计范围仍为 undecided，请尽早用 set_design_scope 判定是装配体还是单个零件"
            if session.design_scope == DesignScope.UNDECIDED
            else (
                "装配体范围：详细计算完成后须用 declare_assembly_parts 列出零件清单，"
                "逐零件建模，全部建完后要求用户手工装配"
                if session.design_scope == DesignScope.ASSEMBLY
                else "单个零件范围：几何完成后直接进入零件级仿真，不需要装配交接"
            )
        ),
    }


class SpecEntry(BaseModel):
    key: str = Field(description="条目 key，须与设计任务书模板一致")
    value: str = Field(
        description="取值。带单位的量请写成 '4 kW'、'1440 r/min'、'16 hour' 形式"
    )
    status: SpecStatus = Field(
        default=SpecStatus.USER_GIVEN,
        description=(
            "user_given=用户明确给出；from_drawing=图纸标注；"
            "assumed_pending_confirm=你取的工程惯用值，待用户确认；confirmed=已确认"
        ),
    )
    rationale: str = Field(
        default="", description="assumed_pending_confirm 时必填，说明取值依据"
    )


class UpdateSpecArgs(BaseModel):
    entries: list[SpecEntry] = Field(description="要记录或更新的设计输入条目")
    source: str = Field(default="", description="信息来源，如 '用户第2轮对话'、'图纸 A1'")


@register(
    "update_design_spec",
    layer=ToolLayer.INTERACTION,
    args_model=UpdateSpecArgs,
    description=(
        "增量记录设计输入，返回更新后的缺失项清单与待确认假设清单。"
        "每当用户提供新条件就立即记录，不要攒着。"
        "信息缺失但不阻塞主线时，可取工程惯用值并标为 assumed_pending_confirm，"
        "但必须写明 rationale——禁止静默假设。"
    ),
)
async def update_design_spec(ctx: ToolContext, args: UpdateSpecArgs) -> dict:
    spec = ctx.session.design_spec
    if not spec.items:
        raise ToolRefusal(
            "尚未建立设计任务书",
            remedy="请先调用 start_design 按零件族模板建立任务书",
        )

    updated, unknown_keys = [], []
    for entry in args.entries:
        if entry.key not in spec.items:
            unknown_keys.append(entry.key)
            continue
        if entry.status == SpecStatus.ASSUMED_PENDING_CONFIRM and not entry.rationale:
            raise ToolRefusal(
                f"条目 {entry.key} 标记为工程假设但未写 rationale",
                remedy="工程假设必须说明取值依据，禁止静默假设",
            )
        spec.upsert(
            entry.key,
            value=entry.value,
            status=entry.status,
            source=args.source,
            rationale=entry.rationale,
        )
        updated.append(entry.key)

    stage = ctx.session.design_stage
    missing_now = spec.missing_required(upto_stage=stage.value)
    missing_all = spec.missing_required()
    pending = spec.pending_confirm()

    out = {
        "status": "ok",
        "updated": updated,
        "known_count": spec.known_count(),
        "total_count": len(spec.items),
        "missing_for_current_stage": [
            {"key": i.key, "label": i.label, "hint": i.hint} for i in missing_now
        ],
        "missing_later_stages": [
            {"key": i.key, "label": i.label, "needed_by_stage": i.needed_by_stage}
            for i in missing_all
            if i not in missing_now
        ],
        "pending_confirmation": [
            {"key": i.key, "label": i.label, "value": i.render_value(), "rationale": i.rationale}
            for i in pending
        ],
    }
    if unknown_keys:
        out["unknown_keys"] = unknown_keys
        out["hint_unknown"] = (
            f"这些 key 不在任务书模板中，已忽略：{unknown_keys}。"
            "可用 key 请看 start_design 返回的 all_items"
        )
    out["ready_for_next_stage"] = not missing_now
    return out


class DecisionOptionArg(BaseModel):
    label: str = Field(description="选项的完整描述，要具体到可执行，不要笼统")
    pros: list[str] = Field(default_factory=list, description="该选项的优点")
    cons: list[str] = Field(default_factory=list, description="该选项的缺点")
    applicability: str = Field(default="", description="适用条件或适用场景")


class RequestDecisionArgs(BaseModel):
    question: str = Field(description="要问用户的问题，一句话说清")
    kind: DecisionKind = Field(
        default=DecisionKind.CLARIFY,
        description=(
            "clarify=澄清设计输入；scheme_choice=方案选择；"
            "gate_approval=评审关口授权；rework_path=校核不通过后的返工路径选择"
        ),
    )
    context: str = Field(
        default="", description="给用户的背景说明：为什么需要这个决策、影响什么"
    )
    options: list[DecisionOptionArg] = Field(
        default_factory=list,
        description=(
            "2~3 个具体选项，各列优劣。"
            "禁止提开放式问题——用户是来做决策的，不是来做填空题的"
        ),
    )
    recommended_index: int | None = Field(
        default=None, description="你推荐的选项序号（0 起）"
    )
    reasoning: str = Field(default="", description="推荐理由，必须结合当前设计输入说明")
    gate: str = Field(
        default="",
        description="若本次是评审关口授权，填 Gate 标识：gate1_scheme_confirmed 等",
    )


@register(
    "request_user_decision",
    layer=ToolLayer.INTERACTION,
    args_model=RequestDecisionArgs,
    interrupts=True,
    description=(
        "向用户提问并暂停设计工作，等待答复后从中断点继续。"
        "用于：澄清缺失的设计输入、请用户在备选方案中决策、请求评审关口授权、"
        "校核不通过时请用户选择返工路径。"
        "提问必须带 2~3 个具体选项、各自优劣与你的推荐及理由。"
        "调用本工具后你本轮的工作即结束，不要再规划后续动作。"
    ),
)
async def request_user_decision(ctx: ToolContext, args: RequestDecisionArgs) -> dict:
    if args.kind != DecisionKind.CLARIFY and len(args.options) < 2:
        raise ToolRefusal(
            f"{args.kind.value} 类决策必须提供至少 2 个具体选项",
            remedy="请列出可行方案并给出各自优缺点与推荐意见后重试",
        )

    decision = PendingDecision(
        decision_id=f"dec-{uuid4().hex[:8]}",
        kind=args.kind,
        question=args.question,
        context=args.context,
        options=[
            DecisionOption(
                label=o.label,
                value=o.label,
                pros=o.pros,
                cons=o.cons,
                applicability=o.applicability,
            )
            for o in args.options
        ],
        recommended_index=args.recommended_index,
        reasoning=args.reasoning,
        gate=args.gate,
        stage=ctx.session.design_stage.value,
    )
    raise ToolInterrupt(decision)


class AlternativeArg(BaseModel):
    name: str = Field(description="方案名称，如 '软齿面方案'")
    summary: str = Field(description="一句话概括")
    structure: str = Field(default="", description="结构形式")
    material: str = Field(default="", description="材料与热处理")
    process: str = Field(default="", description="工艺要求")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    cost_level: str = Field(default="", description="成本量级：低 / 中 / 高")


class ProposeArgs(BaseModel):
    alternatives: list[AlternativeArg] = Field(
        description="2~3 个备选方案，要在结构/材料/工艺上有实质差异"
    )
    recommended_index: int = Field(default=0, description="推荐方案序号（0 起）")
    reasoning: str = Field(description="推荐理由，必须结合设计任务书中的具体条件")


@register(
    "propose_design_alternatives",
    layer=ToolLayer.INTERACTION,
    args_model=ProposeArgs,
    description=(
        "登记备选设计方案及对比结论。方案的定性可行性判断可基于工程经验，"
        "但一旦涉及具体数值仍必须走计算工具。"
        "登记后需用 request_user_decision 请用户选定，不得自行替用户决策。"
    ),
)
async def propose_design_alternatives(ctx: ToolContext, args: ProposeArgs) -> dict:
    if len(args.alternatives) < 2:
        raise ToolRefusal(
            "方案设计阶段至少需要 2 个备选方案",
            remedy="请给出在材料、结构或工艺上有实质差异的另一方案",
        )

    ctx.session.alternatives = [
        SchemeAlternative(
            name=a.name,
            summary=a.summary,
            structure=a.structure,
            material=a.material,
            process=a.process,
            pros=a.pros,
            cons=a.cons,
            cost_level=a.cost_level,
        )
        for a in args.alternatives
    ]
    ctx.say(f"[方案设计] 已登记 {len(args.alternatives)} 个备选方案\n")
    return {
        "status": "ok",
        "count": len(args.alternatives),
        "recommended": args.alternatives[args.recommended_index].name
        if 0 <= args.recommended_index < len(args.alternatives)
        else "",
        "reasoning": args.reasoning,
        "next": "请用 request_user_decision(kind=scheme_choice) 请用户选定方案",
    }


class ConfirmSchemeArgs(BaseModel):
    selected_index: int = Field(description="用户选定的方案序号（0 起）")
    user_statement: str = Field(description="用户选定方案的原话或明确表述")
    adjustments: list[str] = Field(
        default_factory=list, description="用户在选定时附加的调整要求"
    )


@register(
    "confirm_scheme",
    layer=ToolLayer.INTERACTION,
    args_model=ConfirmSchemeArgs,
    description=(
        "记录用户选定的设计方案，通过 Gate 1（方案确认）。"
        "通过后才允许进入详细设计计算阶段。必须在用户明确表态后才调用。"
    ),
)
async def confirm_scheme(ctx: ToolContext, args: ConfirmSchemeArgs) -> dict:
    session = ctx.session
    if not session.alternatives:
        raise ToolRefusal(
            "尚未登记任何备选方案",
            remedy="请先 propose_design_alternatives 给出备选方案供用户选择",
        )
    if not 0 <= args.selected_index < len(session.alternatives):
        raise ToolRefusal(
            f"方案序号 {args.selected_index} 超出范围（共 {len(session.alternatives)} 个）"
        )
    if not args.user_statement.strip():
        raise ToolRefusal(
            "缺少用户表态", remedy="Gate 1 需要记录用户的明示选择，不得代为决定"
        )

    for idx, alt in enumerate(session.alternatives):
        alt.selected = idx == args.selected_index
    selected = session.alternatives[args.selected_index]

    session.approve_gate(
        Gate.SCHEME_CONFIRMED,
        statement=args.user_statement,
        conditions=args.adjustments,
    )
    session.design_stage = DesignStage.DETAIL_CALCULATION
    ctx.say(f"[Gate 1] 方案已确认：{selected.name}\n")

    return {
        "status": "ok",
        "selected_scheme": selected.model_dump(mode="json"),
        "adjustments": args.adjustments,
        "gate": Gate.SCHEME_CONFIRMED.value,
        "stage": session.design_stage.value,
        "next": "进入详细设计计算阶段，按总体设计→齿轮→轴→键→轴承→箱体的顺序推进",
    }


class SetScopeArgs(BaseModel):
    scope: DesignScope = Field(
        description="single_part=单个零件；assembly=装配体（由多个需分别建模的零件组成）"
    )
    reason: str = Field(description="判定理由，须结合用户的设计意图说明")


@register(
    "set_design_scope",
    layer=ToolLayer.INTERACTION,
    args_model=SetScopeArgs,
    description=(
        "判定本项设计的对象范围：单个零件还是装配体。应在设计输入收敛阶段尽早调用。\n"
        "判定依据是用户的设计意图，不是零件族模板："
        "需求只涉及一个可独立加工的零件（一根轴、一块板、一个支架、一个法兰）→ single_part；"
        "需求涉及多个零件的组合、需考虑零件间配合与传动关系（减速器、夹具、机架）→ assembly。\n"
        "两种范围的流程严格度完全相同——都要走设计计算、圆整回代、参数冻结、建模契约、"
        "几何表达、校核验证，都要交付设计说明书与设计计算书。\n"
        "唯一区别在几何之后：single_part 的几何直接进入零件级仿真；"
        "assembly 需逐零件建模，全部建完后由用户手工装配并提交装配体文件，"
        "再进入装配级仿真（当前 mcp-cad 的装配工具链不足以可靠自动装配）。"
    ),
)
async def set_design_scope(ctx: ToolContext, args: SetScopeArgs) -> dict:
    session = ctx.session
    if args.scope == DesignScope.UNDECIDED:
        raise ToolRefusal(
            "不能把设计范围设回 undecided",
            remedy="请明确判定为 single_part 或 assembly",
        )
    if not args.reason.strip():
        raise ToolRefusal(
            "缺少判定理由", remedy="请说明依据用户的哪部分设计意图做出此判定"
        )

    previous = session.design_scope
    if (
        previous != DesignScope.UNDECIDED
        and previous != args.scope
        and session.gate_passed(Gate.PARAMETERS_FROZEN)
    ):
        raise ToolRefusal(
            f"参数已冻结后不能把设计范围从 {previous.value} 改为 {args.scope.value}",
            remedy=(
                "范围变更会改变几何与仿真的组织方式。"
                "如确需变更，请先 unfreeze_parameters 并向用户说明影响"
            ),
        )

    session.design_scope = args.scope
    if args.scope == DesignScope.SINGLE_PART:
        session.part_builds = []
        session.assembly_handoff = AssemblyHandoff()
        session.revoke_gate(Gate.ASSEMBLY_SUBMITTED)

    ctx.say(f"[设计范围] {SCOPE_LABELS[args.scope]}\n")
    out = {
        "status": "ok",
        "previous_scope": previous.value,
        "scope": args.scope.value,
        "scope_label": SCOPE_LABELS[args.scope],
        "reason": args.reason,
    }
    if args.scope == DesignScope.ASSEMBLY:
        out["flow"] = (
            "详细计算 → 参数冻结 → 逐零件 plan_modeling_contract + build_model → "
            "全部零件建完后要求用户手工装配 → submit_assembly_geometry → 装配级 run_simulation"
        )
        out["next"] = (
            "参数冻结后请先用 declare_assembly_parts 登记零件清单，系统据此跟踪逐件建模进度"
        )
    else:
        out["flow"] = (
            "详细计算 → 参数冻结 → plan_modeling_contract + build_model → "
            "零件级 run_simulation → accept_verification → 交付"
        )
        out["next"] = "本范围不需要装配交接，几何完成后可直接仿真"
    return out


class PartDeclArg(BaseModel):
    part_name: str = Field(description="零件名，将作为建模契约的 part_name，须唯一")
    part_type: str = Field(
        default="custom",
        description="shaft / plate / housing / bracket / gear / flange / custom",
    )
    role: str = Field(
        default="", description="在装配体中的功能角色，如 '输入轴'、'大齿轮'、'箱体上盖'"
    )
    note: str = Field(default="", description="建模要点或与相邻零件的配合关系说明")


class DeclarePartsArgs(BaseModel):
    parts: list[PartDeclArg] = Field(
        description="装配体的零件清单，按建模顺序排列（先基准件，后与之配合的件）"
    )
    replace: bool = Field(
        default=False,
        description="true=用本次清单整体替换已有清单；false=增量合并（同名则更新）",
    )


@register(
    "declare_assembly_parts",
    layer=ToolLayer.INTERACTION,
    args_model=DeclarePartsArgs,
    description=(
        "登记装配体的零件清单，系统据此跟踪逐零件建模进度。仅装配体范围可用。\n"
        "只登记需要自己建模的零件——标准件（螺栓、轴承、键、密封圈）不必列入，"
        "它们在装配时由用户从标准件库调用。\n"
        "清单登记后，对每个零件分别调用 plan_modeling_contract + build_model；"
        "系统会在全部零件建完时提示你要求用户手工装配。"
    ),
)
async def declare_assembly_parts(ctx: ToolContext, args: DeclarePartsArgs) -> dict:
    session = ctx.session
    if not session.is_assembly_scope:
        raise ToolRefusal(
            f"当前设计范围是 {session.design_scope.value}，零件清单只对装配体有意义",
            remedy=(
                "若本项设计确实是装配体，请先 set_design_scope(scope=assembly)；"
                "单个零件不需要零件清单"
            ),
        )
    if not args.parts:
        raise ToolRefusal("零件清单不能为空")

    names = [p.part_name.strip() for p in args.parts]
    if any(not n for n in names):
        raise ToolRefusal("零件名不能为空")
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ToolRefusal(
            f"零件名重复：{sorted(duplicates)}",
            remedy="每个零件需唯一命名，因为契约与几何文件按零件名区分",
        )

    if args.replace:
        session.part_builds = []

    added, updated = [], []
    for decl in args.parts:
        existing = session.find_part(decl.part_name)
        if existing is None:
            session.part_builds.append(
                PartBuild(
                    part_name=decl.part_name.strip(),
                    part_type=decl.part_type,
                    role=decl.role,
                    note=decl.note,
                )
            )
            added.append(decl.part_name.strip())
        else:
            existing.part_type = decl.part_type or existing.part_type
            existing.role = decl.role or existing.role
            existing.note = decl.note or existing.note
            updated.append(existing.part_name)

    ctx.say(f"[零件清单] 共 {len(session.part_builds)} 个零件待建模\n")
    return {
        "status": "ok",
        "added": added,
        "updated": updated,
        "parts": [
            {
                "part_name": p.part_name,
                "part_type": p.part_type,
                "role": p.role,
                "status": p.status.value,
                "geometry_file": p.geometry_file,
            }
            for p in session.part_builds
        ],
        "total": len(session.part_builds),
        "built": len(session.built_parts()),
        "next": (
            "对每个零件依次调用 plan_modeling_contract(part_name=...) + build_model。"
            "全部建完后再要求用户手工装配"
        ),
    }


class SetStageArgs(BaseModel):
    stage: DesignStage = Field(description="要切换到的设计阶段")
    reason: str = Field(default="", description="切换理由，说明当前阶段的完成判据已满足")


@register(
    "set_design_stage",
    layer=ToolLayer.INTERACTION,
    args_model=SetStageArgs,
    description=(
        "切换当前设计阶段。系统会按阶段行动手册注入对应的工作要求，"
        "并在需要前置 Gate 的阶段做门控校验。"
        "只有在当前阶段的完成判据确实满足时才切换。"
    ),
)
async def set_design_stage(ctx: ToolContext, args: SetStageArgs) -> dict:
    session = ctx.session
    required = STAGE_REQUIRED_GATE.get(args.stage)
    if required and not session.gate_passed(required):
        gate_hint = {
            Gate.SCHEME_CONFIRMED: "请先 propose_design_alternatives + request_user_decision + confirm_scheme",
            Gate.PARAMETERS_FROZEN: "请先完成全部校核，向用户呈现台账后 freeze_parameters",
            Gate.VERIFICATION_ACCEPTED: "请先完成有限元校核并 accept_verification",
        }[required]
        raise ToolRefusal(
            f"进入「{STAGE_LABELS[args.stage]}」阶段需要先通过 {required.value}",
            remedy=gate_hint,
        )

    if args.stage == DesignStage.ASSEMBLY_HANDOFF and not session.is_assembly_scope:
        raise ToolRefusal(
            "只有装配体范围才有装配交接阶段",
            remedy=(
                "单个零件几何完成后直接进入 verification 阶段做零件级仿真。"
                "若本项设计确实是装配体，请先 set_design_scope(scope=assembly)"
            ),
            details={"scope": session.design_scope.value},
        )

    if args.stage == DesignStage.ASSEMBLY_HANDOFF:
        issues = session.assembly_completeness_issues()
        if issues:
            raise ToolRefusal(
                "装配零件清单未形成完整的单级减速器功能闭环",
                remedy="补齐传动链、箱体、轴承支撑和密封接口后再进入装配交接",
                details={"issues": issues},
            )

    if args.stage == DesignStage.VERIFICATION and session.is_assembly_scope:
        if not session.gate_passed(Gate.ASSEMBLY_SUBMITTED):
            unbuilt = [p.part_name for p in session.unbuilt_parts()]
            raise ToolRefusal(
                "装配体尚未装配完成，不能进入校核验证阶段",
                remedy=(
                    "装配体仿真必须基于真实装配几何。请先逐零件建模完毕，"
                    "再要求用户在 Inventor 中手工装配并保存，"
                    "然后用 submit_assembly_geometry 提交 .iam 或 .stp 路径"
                ),
                details={
                    "parts_total": len(session.part_builds),
                    "parts_built": len(session.built_parts()),
                    "parts_unbuilt": unbuilt,
                },
            )

    if args.stage == DesignStage.SCHEME_DESIGN:
        missing = session.design_spec.missing_required(
            upto_stage=DesignStage.SPEC_GATHERING.value
        )
        if missing:
            raise ToolRefusal(
                f"设计输入尚不完整，仍缺 {len(missing)} 项必填条目："
                f"{[i.label for i in missing]}",
                remedy="请先向用户问清这些条件并 update_design_spec 记录",
            )

    previous = session.design_stage
    session.design_stage = args.stage
    ctx.say(f"[阶段] {STAGE_LABELS[previous]} → {STAGE_LABELS[args.stage]}\n")
    return {
        "status": "ok",
        "previous_stage": previous.value,
        "stage": args.stage.value,
        "stage_label": STAGE_LABELS[args.stage],
        "reason": args.reason,
    }
