"""设计说明书与设计计算书渲染。

文档内容全部来自结构化数据（设计任务书、参数台账、计算记录、仿真报告），
不由模型自由撰写——这样文档里每个数字都自带来源，也不会出现"文档说一套、
台账是另一套"的情况。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.schemas.calculation_record import Verdict
from app.schemas.design_stage import SCOPE_LABELS, STAGE_LABELS
from app.schemas.parameter_ledger import ParameterSource
from app.schemas.session_state import SessionState

SOURCE_LABELS = {
    ParameterSource.USER_GIVEN: "用户给定",
    ParameterSource.FROM_DRAWING: "图纸标注",
    ParameterSource.CALCULATED: "计算所得",
    ParameterSource.STANDARD_LOOKUP: "标准查表",
    ParameterSource.DESIGN_CHOICE: "设计选择",
    ParameterSource.ASSUMED: "工程假设",
}


def ensure_report_inputs_current(session: SessionState) -> None:
    stale_params = [entry.symbol for entry in session.ledger.stale()]
    stale_calcs = [record.record_id for record in session.calculations.values() if record.stale]
    if stale_params or stale_calcs:
        raise ValueError(
            "报告输入包含失效项："
            f"parameters={stale_params}, calculations={stale_calcs}"
        )


def render_design_report(session: SessionState, *, author: str = "") -> str:
    """渲染设计说明书（Markdown）。"""
    ensure_report_inputs_current(session)
    spec = session.design_spec
    title = spec.title or f"{spec.family_label or '零件'}设计说明书"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    parts: list[str] = [
        f"# {title}",
        "",
        f"- 零件族：{spec.family_label or spec.family or '未指定'}",
        f"- 设计范围：{SCOPE_LABELS.get(session.design_scope, session.design_scope.value)}",
        f"- 设计模式：{'正向设计' if session.mode.value == 'design' else '逆向建模'}",
        f"- 当前阶段：{STAGE_LABELS.get(session.design_stage, session.design_stage.value)}",
        f"- 生成时间：{stamp}",
    ]
    if author:
        parts.append(f"- 设计：{author}")
    parts += ["", "---", ""]

    parts += _section_spec(session)
    parts += _section_scheme(session)
    parts += _section_calculations(session)
    parts += _section_ledger(session)
    chapter = 5
    assembly = _section_assembly(session, chapter)
    if assembly:
        parts += assembly
        chapter += 1
    parts += _section_verification(session, chapter)
    parts += _section_deliverables(session, chapter + 1)
    parts += _section_traceability(session)

    return "\n".join(parts)


def render_calculation_book(session: SessionState) -> str:
    """渲染设计计算书（Markdown），逐条展开计算记录全文。"""
    spec = session.design_spec
    ensure_report_inputs_current(session)
    title = f"{spec.family_label or '零件'}设计计算书"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    parts = [f"# {title}", "", f"生成时间：{stamp}", ""]
    records = _ordered_records(session)
    if not records:
        parts.append("（尚无计算记录）")
        return "\n".join(parts)

    parts += [
        f"共 {len(records)} 条计算记录，"
        f"其中校核项 {sum(1 for r in records if r.verdict != Verdict.NOT_APPLICABLE)} 项。",
        "",
        "---",
        "",
    ]

    grouped: dict[str, list] = {}
    for record in records:
        category = _category_of(record)
        grouped.setdefault(category, []).append(record)

    for chapter, (category, items) in enumerate(grouped.items(), start=1):
        parts += [f"## {chapter} {category}", ""]
        for record in items:
            parts += [record.render_full(), ""]
            if record.stale:
                parts += [f"> ⚠ 本条已失效：{record.stale_reason}", ""]
            if record.script:
                parts += ["计算脚本：", "", "```python", record.script.strip(), "```", ""]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 章节
# ---------------------------------------------------------------------------


def _section_spec(session: SessionState) -> list[str]:
    spec = session.design_spec
    out = ["## 1 设计输入", ""]
    if not spec.items:
        return out + ["（未记录设计任务书）", ""]

    groups: dict[str, list] = {}
    for item in spec.items.values():
        if item.is_known:
            groups.setdefault(item.group, []).append(item)

    if not groups:
        return out + ["（设计任务书为空）", ""]

    for group, items in groups.items():
        out += [f"### {group}", "", "| 条目 | 取值 | 来源 | 说明 |", "| --- | --- | --- | --- |"]
        for item in items:
            note = item.rationale or item.hint or ""
            flag = "⚠待确认 " if item.needs_confirm else ""
            out.append(
                f"| {item.label or item.key} | {item.render_value()} "
                f"| {flag}{item.status.value} | {note} |"
            )
        out.append("")

    pending = spec.pending_confirm()
    if pending:
        out += ["### 待确认的工程假设", ""]
        out += [f"- {i.label}：{i.render_value()}（{i.rationale}）" for i in pending]
        out.append("")
    return out


def _section_scheme(session: SessionState) -> list[str]:
    if not session.alternatives:
        return []
    out = ["## 2 方案设计与选择", "", "| 方案 | 结构 | 材料与热处理 | 成本 | 是否选定 |", "| --- | --- | --- | --- | --- |"]
    for alt in session.alternatives:
        out.append(
            f"| {alt.name} | {alt.structure or alt.summary} | {alt.material} "
            f"| {alt.cost_level} | {'✓ 选定' if alt.selected else '—'} |"
        )
    out.append("")

    for alt in session.alternatives:
        out += [f"### {alt.name}", ""]
        if alt.summary:
            out += [alt.summary, ""]
        if alt.pros:
            out += ["优点：", ""] + [f"- {p}" for p in alt.pros] + [""]
        if alt.cons:
            out += ["缺点：", ""] + [f"- {c}" for c in alt.cons] + [""]
        if alt.process:
            out += [f"工艺要求：{alt.process}", ""]

    gate = session.gates.get("gate1_scheme_confirmed")
    if gate and gate.approved:
        out += [
            "### 方案确认记录",
            "",
            f"- 用户表述：{gate.user_statement}",
            f"- 确认时间：{gate.approved_at}",
        ]
        if gate.conditions:
            out += [f"- 附加要求：{'；'.join(gate.conditions)}"]
        out.append("")
    return out


def _section_calculations(session: SessionState) -> list[str]:
    records = _ordered_records(session)
    if not records:
        return ["## 3 设计计算", "", "（尚无计算记录）", ""]

    out = ["## 3 设计计算", "", "计算摘要（详细过程见《设计计算书》）：", ""]
    out += ["| 编号 | 计算项 | 结果 | 判据结论 | 余量 | 依据 |", "| --- | --- | --- | --- | --- | --- |"]
    for record in records:
        res = "，".join(f"{k}={v.render()}" for k, v in record.result.items()) or "—"
        verdict = {"pass": "满足", "fail": "不满足", "n/a": "—"}[record.verdict.value]
        margin = f"{record.margin_percent:.1f}%" if record.margin_percent is not None else "—"
        stale = " ⚠失效" if record.stale else ""
        out.append(
            f"| {record.record_id} | {record.title}{stale} | {res} "
            f"| {verdict} | {margin} | {record.source or '—'} |"
        )
    out.append("")

    failed = [r for r in records if r.verdict == Verdict.FAIL]
    if failed:
        out += ["> ⚠ 存在未通过的校核项：", ""]
        out += [f"> - {r.record_id} {r.title}" for r in failed]
        out.append("")
    return out


def _section_ledger(session: SessionState) -> list[str]:
    ledger = session.ledger
    out = ["## 4 设计参数汇总", ""]
    if not ledger.entries:
        return out + ["（台账为空）", ""]

    state = "已冻结" if ledger.is_frozen else "未冻结"
    out += [f"台账状态：{state}；共 {len(ledger.entries)} 项参数。", ""]

    groups: dict[str, list] = {}
    for entry in ledger.entries.values():
        groups.setdefault(entry.group, []).append(entry)

    for group, entries in groups.items():
        out += [
            f"### {group}",
            "",
            "| 符号 | 名称 | 取值 | 来源 | 依据 | 说明 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for e in entries:
            out.append(
                f"| {e.symbol} | {e.name or '—'} | {e.value.render()} "
                f"| {SOURCE_LABELS.get(e.source, e.source.value)} "
                f"| {', '.join(e.basis) or '—'} | {e.rationale or '—'} |"
            )
        out.append("")

    assumed = ledger.assumed()
    if assumed:
        out += ["### 工程假设清单", ""]
        out += [f"- {e.symbol}（{e.name}）= {e.value.render()}：{e.rationale}" for e in assumed]
        out.append("")

    gate = session.gates.get("gate2_parameters_frozen")
    if gate and gate.approved:
        out += [
            "### 参数冻结记录",
            "",
            f"- 用户授权：{gate.user_statement}",
            f"- 冻结时间：{gate.approved_at}",
            "",
        ]
    return out


def _section_assembly(session: SessionState, chapter: int) -> list[str]:
    """装配体的零件组成与装配交接记录。装配由用户手工完成，须如实记录。"""
    if not session.is_assembly_scope:
        return []

    out = [f"## {chapter} 装配组成与装配交接", ""]
    parts = session.part_builds
    if not parts:
        out += ["（未登记零件清单）", ""]
    else:
        out += [
            f"本装配体由 {len(parts)} 个自建零件组成"
            f"（标准件按台账选型，由装配时调用标准件库）：",
            "",
            "| 零件 | 作用 | 状态 | 几何文件 |",
            "| --- | --- | --- | --- |",
        ]
        for p in parts:
            out.append(
                f"| {p.part_name} | {p.role or '—'} | "
                f"{'已建模' if p.is_built else p.status.value} | "
                f"{f'`{p.geometry_file}`' if p.geometry_file else '—'} |"
            )
        out.append("")
    handoff = session.assembly_handoff
    out += ["### 装配交接记录", ""]
    if not handoff.submitted:
        return out + ["（装配尚未交接，装配级校核结论不成立）", ""]

    source_label = {"iam": "Inventor 装配体（.iam）", "stp": "用户导出的 STEP"}.get(
        handoff.source_kind, handoff.source_kind or "—"
    )
    out += [
        "装配由用户在 Inventor 中手工完成——本系统的 CAD 工具链不具备可靠的自动装配能力，"
        "装配关系的正确性由用户负责。",
        "",
        f"- 提交形式：{source_label}",
    ]
    if handoff.iam_file:
        out.append(f"- 源装配体：`{handoff.iam_file}`")
    out += [
        f"- 装配体几何：`{handoff.step_file}`",
        f"- 几何校验值：`{handoff.step_hash[:16] or '—'}`",
        f"- 用户确认：{handoff.user_statement or '—'}",
        f"- 交接时间：{handoff.submitted_at or '—'}",
    ]
    if handoff.notes:
        out += ["- 用户说明的装配偏差："] + [f"  - {n}" for n in handoff.notes]
    out.append("")
    return out


def _section_verification(session: SessionState, chapter: int) -> list[str]:
    report = session.simulation_report
    out = [f"## {chapter} 校核验证", ""]
    if report is None:
        return out + ["（尚未进行有限元校核）", ""]

    out += [
        f"- 几何文件：`{report.geometry_file}`",
        f"- 校核结论：{report.pass_or_fail.value}",
        "",
    ]
    if report.result_items:
        out += ["| 结果项 | 数值 | 单位 | 限值 | 结论 | 说明 |", "| --- | --- | --- | --- | --- | --- |"]
        for item in report.result_items:
            out.append(
                f"| {item.name} | {item.value if item.value is not None else '—'} "
                f"| {item.unit or '—'} | {item.limit if item.limit is not None else '—'} "
                f"| {'满足' if item.passed else '不满足'} | {item.detail or '—'} |"
            )
        out.append("")
    if report.issues:
        out += ["发现的问题：", ""] + [f"- {i}" for i in report.issues] + [""]
    if report.recommended_adjustments:
        out += ["建议调整：", ""] + [f"- {a}" for a in report.recommended_adjustments] + [""]

    comparison = session.semantic_facts.get("verification_comparison")
    if comparison:
        out += ["### 解析校核与有限元结果对比", "", str(comparison), ""]

    gate = session.gates.get("gate3_verification_accepted")
    if gate and gate.approved:
        out += ["### 校核受理记录", "", f"- 用户表述：{gate.user_statement}", f"- 受理时间：{gate.approved_at}"]
        if gate.conditions:
            out += ["- 遗留风险："] + [f"  - {c}" for c in gate.conditions]
        out.append("")
    return out


def _section_deliverables(session: SessionState, chapter: int) -> list[str]:
    if not session.deliverables:
        return []
    out = [
        f"## {chapter} 交付物清单",
        "",
        "| 类型 | 名称 | 路径 |",
        "| --- | --- | --- |",
    ]
    for d in session.deliverables:
        out.append(f"| {d.kind} | {d.title} | `{d.path}` |")
    out.append("")
    return out


def _section_traceability(session: SessionState) -> list[str]:
    """溯源自检：把无依据的参数暴露出来，而不是藏起来。"""
    ledger = session.ledger
    problems: list[str] = []

    for entry in ledger.entries.values():
        if entry.source in (ParameterSource.CALCULATED, ParameterSource.STANDARD_LOOKUP):
            if not entry.basis:
                problems.append(f"参数 {entry.symbol} 声明为{SOURCE_LABELS[entry.source]}但无依据")
        if entry.status.value == "stale":
            problems.append(f"参数 {entry.symbol} 已失效：{entry.stale_reason}")

    for record in session.calculations.values():
        if not record.source:
            problems.append(f"计算记录 {record.record_id} 未标注出处")
        if record.stale:
            problems.append(f"计算记录 {record.record_id} 已失效：{record.stale_reason}")

    pending = session.design_spec.pending_confirm()
    problems += [f"设计输入 {i.label} 仍为未确认的工程假设" for i in pending]

    out = ["## 附录 A 溯源自检", ""]
    if not problems:
        out += ["本设计的全部参数均可追溯到计算记录、标准条款或用户确认，无遗留问题。", ""]
    else:
        out += [f"发现 {len(problems)} 项溯源问题，需在定稿前处理：", ""]
        out += [f"{i}. {p}" for i, p in enumerate(problems, start=1)]
        out.append("")
    return out


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _ordered_records(session: SessionState) -> list:
    def seq(record) -> int:
        try:
            return int(record.record_id.split("#")[-1])
        except (ValueError, IndexError):
            return 0

    return sorted(session.calculations.values(), key=seq)


_CATEGORY_KEYWORDS = [
    ("总体设计", ("效率", "电动机", "转矩", "传动比", "转速", "寿命", "循环")),
    ("齿轮传动", ("齿", "模数", "中心距", "接触", "弯曲", "分度圆")),
    ("轴的设计", ("轴", "弯矩", "挠度", "截面", "刚度")),
    ("键连接", ("键", "挤压", "剪切")),
    ("轴承", ("轴承", "当量动载荷", "寿命系数")),
    ("箱体", ("箱", "壁厚", "凸缘", "螺栓", "地脚")),
]


def _category_of(record) -> str:
    haystack = f"{record.title} {record.formula_id}"
    for name, keywords in _CATEGORY_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return name
    return "其他计算"


def write_markdown(content: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
