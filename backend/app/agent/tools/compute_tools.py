"""计算层与台账层工具。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.calculation_record import Verdict
from app.schemas.common import Quantity
from app.schemas.design_stage import Gate
from app.schemas.parameter_ledger import ParameterSource, ParameterStatus
from app.services.compute import formula_lib, sandbox
from app.services.compute import ledger as ledger_svc
from app.services.compute import units as U

from .registry import ToolContext, ToolLayer, ToolRefusal, hard_gate_enabled, register


class QuantityInput(BaseModel):
    """带单位的输入量。单位必须与公式声明一致或量纲兼容，系统会自动换算。"""

    value: float = Field(description="数值")
    unit: str = Field(
        default="",
        description="单位，如 mm / kW / r/min / N*mm / MPa / hour。无量纲量留空",
    )

    def to_quantity(self) -> Quantity:
        return Quantity(value=self.value, unit=self.unit)


def _to_quantities(raw: dict[str, QuantityInput]) -> dict[str, Quantity]:
    return {k: v.to_quantity() for k, v in raw.items()}


class SolveFormulaArgs(BaseModel):
    formula_id: str = Field(description="公式库中的公式 ID，由 search_formula 获得")
    inputs: dict[str, QuantityInput] = Field(
        description=(
            "按公式符号名提供输入，每项含 value 与 unit。"
            "有默认值的符号可省略；符号名必须与公式卡片一致"
        )
    )
    title: str = Field(default="", description="本次计算的中文标题，用于计算书章节名")
    solve_for: str = Field(default="", description="求解目标符号，留空则取公式默认输出")
    depends_on: list[str] = Field(
        default_factory=list,
        description="本次计算依赖的其他计算记录 ID 或台账参数符号，用于变更失效传播",
    )


@register(
    "solve_formula",
    layer=ToolLayer.COMPUTE,
    args_model=SolveFormulaArgs,
    description=(
        "按公式库中的公式求解，返回带出处、代入过程与判据结论的计算记录。"
        "这是获得设计数值的唯一正当途径——你不得自己心算后直接报数，"
        "因为心算的数字没有计算记录、无法写入计算书、参数变更时无法重算。"
        "若公式是校核类（is_check），系统会自动代入判据判定通过与否并给出余量百分比。"
    ),
)
async def solve_formula(ctx: ToolContext, args: SolveFormulaArgs) -> dict:
    if hard_gate_enabled(ctx) and not ctx.session.gate_passed(Gate.SCHEME_CONFIRMED):
        raise ToolRefusal(
            "设计方案尚未确认，不能进入详细计算",
            remedy="请先登记备选方案并取得用户明确选择后调用 confirm_scheme",
        )
    inputs = _to_quantities(args.inputs)
    record_id = ctx.session.next_calc_id()

    try:
        record = formula_lib.solve(
            args.formula_id,
            inputs,
            record_id=record_id,
            solve_for=args.solve_for,
            title=args.title,
            extra_known=inputs,
            depends_on=args.depends_on,
        )
    except formula_lib.FormulaError as exc:
        ctx.session.calc_seq -= 1
        raise ToolRefusal(
            str(exc),
            remedy="请用 search_formula 取回该公式的完整符号定义后修正入参再试",
        ) from exc
    except U.UnitError as exc:
        ctx.session.calc_seq -= 1
        raise ToolRefusal(
            f"单位错误：{exc}",
            remedy="请检查每个输入的 unit 是否与公式声明的量纲一致",
        ) from exc

    ledger_svc.record_calculation(ctx.session, record)
    ctx.say(f"[{record.record_id}] {record.render_line()}\n")

    out = {
        "status": "ok",
        "record_id": record.record_id,
        "title": record.title,
        "result": {k: v.model_dump() for k, v in record.result.items()},
        "result_text": {k: v.render() for k, v in record.result.items()},
        "substitution": record.substitution,
        "source": record.source,
        "verdict": record.verdict.value,
        "margin_percent": record.margin_percent,
        "notes": record.notes,
    }
    if record.verdict == Verdict.FAIL:
        out["attention"] = (
            "校核不通过。请说明超出程度，并给出可选的调整路径（加大尺寸/改材料/"
            "改热处理/调齿宽系数等）及各自代价，再请用户决策，不要自行降低判据。"
        )
    if not record.verdict == Verdict.NOT_APPLICABLE:
        out["reminder"] = "若后续圆整了任何输入参数，本条校核需要回代重算"
    else:
        out["reminder"] = (
            "计算原值通常不能直接使用，请用 lookup_standard_series 圆整后再落账"
        )
    return out


class RunCalculationArgs(BaseModel):
    title: str = Field(description="本次计算的中文标题，用于计算书章节名")
    script: str = Field(
        description=(
            "Python 计算脚本。可直接使用 math / np / sp / optimize / integrate / "
            "interpolate，无需也禁止 import。必须把结论写入 outputs 字典，"
            "例如 outputs['L10h'] = 64200.0"
        )
    )
    inputs: dict[str, QuantityInput] = Field(
        default_factory=dict,
        description="注入脚本命名空间的输入量（按符号名注入其数值），用于留下代入记录",
    )
    expected_outputs: list[str] = Field(
        default_factory=list, description="期望产出的变量名，作为 outputs 字典的兜底"
    )
    output_units: dict[str, str] = Field(
        default_factory=dict, description="各输出量的单位，如 {'L10h': 'hour'}"
    )
    source: str = Field(
        default="",
        description="计算依据出处，如教材条目或标准号。非标计算也必须说明依据来源",
    )
    criterion: str = Field(default="", description="判据文字描述（若为校核计算）")
    depends_on: list[str] = Field(
        default_factory=list, description="依赖的计算记录 ID 或台账参数符号"
    )


@register(
    "run_calculation",
    layer=ToolLayer.COMPUTE,
    args_model=RunCalculationArgs,
    description=(
        "在受限沙箱中执行数值/符号计算，用于公式库未覆盖的非标计算："
        "参数扫描、非线性求根、数值积分、符号推导、多工况对比等。"
        "同样产出可追溯的计算记录。沙箱只允许纯计算，禁止文件、网络、import。"
        "凡公式库里有的计算一律优先用 solve_formula，因为那样才有标准出处。"
    ),
)
async def run_calculation(ctx: ToolContext, args: RunCalculationArgs) -> dict:
    record_id = ctx.session.next_calc_id()
    try:
        record = await sandbox.run_script(
            args.script,
            record_id=record_id,
            title=args.title,
            inputs=_to_quantities(args.inputs),
            expected_outputs=args.expected_outputs,
            output_units=args.output_units,
            source=args.source,
            criterion=args.criterion,
            depends_on=args.depends_on,
        )
    except sandbox.SandboxError as exc:
        ctx.session.calc_seq -= 1
        raise ToolRefusal(
            str(exc), remedy="请修正脚本后重试，或改用 solve_formula 走标准公式"
        ) from exc

    ledger_svc.record_calculation(ctx.session, record)
    ctx.say(f"[{record.record_id}] {record.render_line()}\n")

    return {
        "status": "ok",
        "record_id": record.record_id,
        "title": record.title,
        "result": {k: v.model_dump() for k, v in record.result.items()},
        "result_text": {k: v.render() for k, v in record.result.items()},
        "stdout": record.notes,
        "source": record.source,
        "reminder": (
            "沙箱计算没有标准出处背书，落账时请在 rationale 中写清计算依据"
        ),
    }


class CommitParameterArgs(BaseModel):
    symbol: str = Field(description="参数符号，如 d_1 / m_n / z_1 / d_shaft_min")
    name: str = Field(default="", description="参数中文名称，如 '小齿轮分度圆直径'")
    value: QuantityInput = Field(description="参数值（含单位）")
    source: ParameterSource = Field(
        description=(
            "来源：user_given(用户给定) / from_drawing(图纸标注) / "
            "calculated(计算所得) / standard_lookup(标准查表) / "
            "design_choice(设计选择) / assumed(工程假设)"
        )
    )
    basis: list[str] = Field(
        default_factory=list,
        description=(
            "依据清单。calculated 必须含至少一条 calc#N 计算记录 ID；"
            "standard_lookup 必须含标准号（如 GB/T 1357-2008）"
        ),
    )
    rationale: str = Field(
        default="",
        description=(
            "取值理由。design_choice 与 assumed 必填，"
            "例如 '软齿面取 24 齿，兼顾重合度与齿轮尺寸'"
        ),
    )
    group: str = Field(
        default="其他",
        description="分组：总体 / 齿轮 / 轴 / 键 / 轴承 / 箱体 / 其他",
    )


@register(
    "commit_parameter",
    layer=ToolLayer.LEDGER,
    args_model=CommitParameterArgs,
    description=(
        "把一个设计参数写入参数台账。所有将进入几何或交付物的参数都必须经此落账。"
        "系统会强制校验依据：计算所得必须指向真实存在的计算记录，查表所得必须给出"
        "标准号，设计选择与工程假设必须写明理由。无依据的数字会被拒绝。"
        "若参数值发生变化，系统会沿依赖图自动标记受影响的计算结论为失效。"
    ),
)
async def commit_parameter(ctx: ToolContext, args: CommitParameterArgs) -> dict:
    try:
        entry = ledger_svc.commit_parameter(
            ctx.session,
            symbol=args.symbol,
            value=args.value.to_quantity(),
            source=args.source,
            name=args.name,
            basis=args.basis,
            rationale=args.rationale,
            group=args.group,
            evidence_required=bool(ctx.extras.get("experiment_flags", {}).get("evidence_required", True)),
            propagation_mode=str(
                ctx.extras.get("experiment_flags", {}).get("propagation_mode", "recursive")
            ),
        )
    except ledger_svc.LedgerError as exc:
        raise ToolRefusal(str(exc)) from exc

    ctx.say(f"[台账] {entry.render_line()}\n")
    stale = ledger_svc.stale_summary(ctx.session)
    out = {
        "status": "ok",
        "symbol": entry.symbol,
        "value": entry.value.render(),
        "entry_status": entry.status.value,
        "revision": entry.revision,
        "ledger_counts": ctx.session.ledger.counts(),
    }
    if entry.revision > 1:
        out["superseded"] = entry.superseded_value
    if stale["stale_calculations"] or stale["stale_parameters"]:
        out["invalidated"] = stale
        out["attention"] = (
            "该参数变更导致上述计算结论与参数失效，必须重算后才能继续推进"
        )
    return out


class QueryLedgerArgs(BaseModel):
    symbols: list[str] = Field(
        default_factory=list, description="要查询的参数符号，留空则返回全部台账快照"
    )
    only_status: str = Field(
        default="",
        description="按状态过滤：tentative / confirmed / frozen / stale",
    )


@register(
    "query_ledger",
    layer=ToolLayer.LEDGER,
    args_model=QueryLedgerArgs,
    description=(
        "查询参数台账。用于确认某参数当前值与状态、检查是否有失效项、"
        "或在参数汇总阶段取出完整清单。"
    ),
)
async def query_ledger(ctx: ToolContext, args: QueryLedgerArgs) -> dict:
    ledger = ctx.session.ledger
    if args.symbols:
        found = {}
        missing = []
        for symbol in args.symbols:
            entry = ledger.get(symbol)
            if entry is None:
                missing.append(symbol)
            else:
                found[symbol] = entry.model_dump(mode="json")
        return {
            "status": "ok",
            "entries": found,
            "missing": missing,
            "is_frozen": ledger.is_frozen,
        }

    entries = list(ledger.entries.values())
    if args.only_status:
        entries = [e for e in entries if e.status.value == args.only_status]

    return {
        "status": "ok",
        "counts": ledger.counts(),
        "is_frozen": ledger.is_frozen,
        "snapshot": ledger.render_snapshot(),
        "entries": [e.model_dump(mode="json") for e in entries],
        "assumed_parameters": [e.symbol for e in ledger.assumed()],
        "stale_parameters": [e.symbol for e in ledger.stale()],
    }


class GetCalcArgs(BaseModel):
    record_ids: list[str] = Field(
        default_factory=list,
        description="计算记录 ID 列表，如 ['calc#7']。留空则返回全部记录的索引",
    )


@register(
    "get_calculation_record",
    layer=ToolLayer.COMPUTE,
    args_model=GetCalcArgs,
    description=(
        "取回计算记录全文（公式、出处、代入过程、判据结论）。"
        "校核不通过需要回溯原因、或需要引用某次计算的细节时使用。"
    ),
)
async def get_calculation_record(ctx: ToolContext, args: GetCalcArgs) -> dict:
    calcs = ctx.session.calculations
    if not args.record_ids:
        return {
            "status": "ok",
            "index": [r.render_line() for r in calcs.values()],
            "verdict_counts": ctx.session.check_verdicts(),
        }
    found = {}
    missing = []
    for rid in args.record_ids:
        record = calcs.get(rid)
        if record is None:
            missing.append(rid)
        else:
            found[rid] = {
                "full_text": record.render_full(),
                "verdict": record.verdict.value,
                "stale": record.stale,
                "stale_reason": record.stale_reason,
                "depends_on": record.depends_on,
                "script": record.script,
            }
    return {"status": "ok", "records": found, "missing": missing}


class FreezeArgs(BaseModel):
    user_statement: str = Field(
        description="用户授权冻结的原话或明确表述，作为 Gate 2 的通过记录"
    )
    confirm_assumptions: bool = Field(
        default=False,
        description="是否同时把设计任务书中所有待确认假设标记为已确认",
    )


@register(
    "freeze_parameters",
    layer=ToolLayer.LEDGER,
    args_model=FreezeArgs,
    description=(
        "冻结参数台账，通过 Gate 2（参数冻结）。冻结后才允许进入几何表达阶段。"
        "调用前必须已经：向用户完整呈现台账、逐项确认所有工程假设、"
        "列出全部校核结论与安全余量，并取得用户的明示授权。"
        "系统会拒绝在存在失效参数或校核不通过时冻结。"
    ),
)
async def freeze_parameters(ctx: ToolContext, args: FreezeArgs) -> dict:
    session = ctx.session
    ledger = session.ledger

    if not ledger.entries:
        raise ToolRefusal(
            "台账为空，没有可冻结的参数",
            remedy="请先完成设计计算并用 commit_parameter 落账",
        )

    stale = []
    if hard_gate_enabled(ctx):
        stale = ledger.stale()
    if stale:
        raise ToolRefusal(
            f"存在 {len(stale)} 个已失效参数：{[e.symbol for e in stale]}",
            remedy="请先重算这些参数（及其依赖的校核）后再冻结",
        )

    stale_calcs = [r.record_id for r in session.calculations.values() if r.stale]
    if hard_gate_enabled(ctx) and stale_calcs:
        raise ToolRefusal(
            f"存在 {len(stale_calcs)} 条已失效的计算记录：{stale_calcs}",
            remedy="这些计算的输入已变更，请回代重算后再冻结",
        )

    failed = session.failed_checks()
    if hard_gate_enabled(ctx) and failed:
        raise ToolRefusal(
            f"存在 {len(failed)} 项校核未通过："
            f"{[f'{r.record_id} {r.title}' for r in failed]}",
            remedy=(
                "校核不通过不得冻结参数。请调整设计参数后重算，"
                "或向用户说明并取得明确的例外授权"
            ),
        )

    if hard_gate_enabled(ctx) and not args.user_statement.strip():
        raise ToolRefusal(
            "缺少用户授权表述",
            remedy="Gate 2 需要记录用户的明示同意，请先 request_user_decision 征询",
        )

    statement = args.user_statement.strip() or "E5 C2: code gate disabled"
    frozen = ledger.freeze(statement)
    confirmed = (
        session.design_spec.confirm_all_assumed(statement)
        if args.confirm_assumptions
        else []
    )
    session.approve_gate(Gate.PARAMETERS_FROZEN, statement=statement)

    ctx.say(f"[Gate 2] 参数台账已冻结，共 {len(frozen)} 项\n")
    return {
        "status": "ok",
        "frozen_count": len(frozen),
        "frozen_symbols": frozen,
        "confirmed_assumptions": confirmed,
        "gate": Gate.PARAMETERS_FROZEN.value,
        "next": "可以进入几何表达阶段，调用 plan_modeling_contract 生成建模契约",
    }


class UnfreezeArgs(BaseModel):
    reason: str = Field(description="解冻原因，如 '有限元校核显示轴根应力超限，需返工'")
    user_statement: str = Field(default="", description="用户同意返工的表述")


@register(
    "unfreeze_parameters",
    layer=ToolLayer.LEDGER,
    args_model=UnfreezeArgs,
    description=(
        "解冻参数台账以便返工重算。仅在校核不通过、需要修改已冻结参数时使用。"
        "解冻会撤销 Gate 2，几何与交付物需要在重新冻结后重做。"
    ),
)
async def unfreeze_parameters(ctx: ToolContext, args: UnfreezeArgs) -> dict:
    session = ctx.session
    if not session.ledger.is_frozen:
        return {"status": "ok", "message": "台账当前未冻结，无需解冻"}

    session.ledger.unfreeze(args.reason)
    session.revoke_gate(Gate.PARAMETERS_FROZEN)
    session.revoke_gate(Gate.VERIFICATION_ACCEPTED)
    ctx.say(f"[Gate 2 撤销] 台账已解冻：{args.reason}\n")
    return {
        "status": "ok",
        "reason": args.reason,
        "user_statement": args.user_statement,
        "revoked_gates": [Gate.PARAMETERS_FROZEN.value, Gate.VERIFICATION_ACCEPTED.value],
        "next": "请重算受影响的参数，重新校核后再次 freeze_parameters",
    }


class ConfirmParamsArgs(BaseModel):
    symbols: list[str] = Field(
        default_factory=list,
        description="要确认的参数符号，留空则确认全部 tentative 参数",
    )


@register(
    "confirm_parameters",
    layer=ToolLayer.LEDGER,
    args_model=ConfirmParamsArgs,
    description=(
        "把台账中的临时参数（tentative）标记为已确认（confirmed）。"
        "参数经回代校核通过、确认不再变动后调用。"
    ),
)
async def confirm_parameters(ctx: ToolContext, args: ConfirmParamsArgs) -> dict:
    changed = ctx.session.ledger.confirm(args.symbols or None)
    return {
        "status": "ok",
        "confirmed": changed,
        "counts": ctx.session.ledger.counts(),
        "still_tentative": [
            e.symbol
            for e in ctx.session.ledger.by_status(ParameterStatus.TENTATIVE)
        ],
    }
