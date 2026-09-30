"""交付层工具：生成设计说明书与设计计算书。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.schemas.common import Deliverable
from app.schemas.design_stage import DesignStage, Gate, SessionMode
from app.services.report import docx_export, renderer

from .registry import ToolContext, ToolLayer, ToolRefusal, hard_gate_enabled, register


def _output_dir(session) -> Path:
    base = os.getenv("DESIGN_REPORT_DIR", "").strip()
    root = Path(base) if base else Path("workspace") / "reports"
    return root / str(session.session_id)


class GenerateReportArgs(BaseModel):
    author: str = Field(default="", description="设计人署名，可留空")
    include_calculation_book: bool = Field(
        default=True, description="是否同时生成《设计计算书》"
    )
    export_docx: bool = Field(
        default=True, description="是否同时导出 docx（除 Markdown 外）"
    )
    force: bool = Field(
        default=False,
        description=(
            "在 Gate 3 未通过时强制生成草稿。仅用于用户明确要求出阶段性草稿的情况，"
            "生成的文档会标注为未定稿"
        ),
    )


@register(
    "generate_design_report",
    layer=ToolLayer.DELIVERY,
    args_model=GenerateReportArgs,
    description=(
        "生成设计说明书与设计计算书。内容全部取自设计任务书、参数台账、计算记录与"
        "仿真报告，你不需要也不应该自己撰写数据——文档里每个数字都会自动带上来源。"
        "文档末尾的溯源自检章节会列出所有无依据的参数与未确认的假设。"
        "前置条件：Gate 3（校核受理）已通过，除非用户明确要求出草稿并设置 force=true。"
    ),
)
async def generate_design_report(ctx: ToolContext, args: GenerateReportArgs) -> dict:
    session = ctx.session
    spec = session.design_spec

    if not spec.items and not session.ledger.entries:
        raise ToolRefusal(
            "既无设计任务书也无参数台账，没有可写入文档的内容",
            remedy="请先完成设计输入收敛与设计计算",
        )

    try:
        renderer.ensure_report_inputs_current(session)
    except ValueError as exc:
        raise ToolRefusal(
            str(exc),
            remedy="请先重算全部失效参数和计算记录，再生成报告",
        ) from exc

    gate_ok = session.gate_passed(Gate.VERIFICATION_ACCEPTED) or not hard_gate_enabled(ctx)
    if not gate_ok and not args.force and hard_gate_enabled(ctx):
        raise ToolRefusal(
            "校核尚未受理（Gate 3 未通过），不能生成正式设计说明书",
            remedy=(
                "请先完成有限元校核并 accept_verification；"
                "若用户明确要求阶段性草稿，可用 force=true 生成未定稿版本"
            ),
            details={
                "has_simulation": session.simulation_report is not None,
                "failed_checks": [r.title for r in session.failed_checks()],
            },
        )

    out_dir = _output_dir(session)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    draft_mark = "" if gate_ok else "_草稿"
    written: list[Deliverable] = []

    report_md = renderer.render_design_report(session, author=args.author)
    if not gate_ok:
        report_md = (
            "> **未定稿草稿** —— 校核尚未受理，本文档仅供阶段性讨论，不得作为设计依据。\n\n"
            + report_md
        )
    md_path = renderer.write_markdown(
        report_md, out_dir / f"设计说明书{draft_mark}_{stamp}.md"
    )
    written.append(
        Deliverable(
            kind="design_report",
            title="设计说明书" + ("（草稿）" if not gate_ok else ""),
            path=str(md_path),
            created_at=stamp,
        )
    )

    if args.include_calculation_book:
        book_md = renderer.render_calculation_book(session)
        book_path = renderer.write_markdown(
            book_md, out_dir / f"设计计算书{draft_mark}_{stamp}.md"
        )
        written.append(
            Deliverable(
                kind="calculation_book",
                title="设计计算书" + ("（草稿）" if not gate_ok else ""),
                path=str(book_path),
                created_at=stamp,
            )
        )

    docx_note = ""
    if args.export_docx:
        for item in list(written):
            try:
                docx_path = docx_export.markdown_to_docx(
                    Path(item.path).read_text(encoding="utf-8"),
                    Path(item.path).with_suffix(".docx"),
                )
                written.append(
                    Deliverable(
                        kind=f"{item.kind}_docx",
                        title=item.title + "（docx）",
                        path=str(docx_path),
                        created_at=stamp,
                    )
                )
            except docx_export.DocxUnavailable as exc:
                docx_note = str(exc)
                break

    session.deliverables.extend(written)
    if gate_ok:
        session.design_stage = DesignStage.COMPLETED

    ctx.say(f"[交付物] 已生成 {len(written)} 个文件于 {out_dir}\n")

    self_check = _self_check(session)
    out = {
        "status": "ok",
        "is_draft": not gate_ok,
        "output_dir": str(out_dir),
        "files": [{"kind": d.kind, "title": d.title, "path": d.path} for d in written],
        "self_check": self_check,
        "stage": session.design_stage.value,
    }
    if docx_note:
        out["docx_warning"] = docx_note
    if self_check["problem_count"]:
        out["attention"] = (
            "溯源自检发现问题（见文档附录 A），请向用户如实说明，不要略过"
        )
    else:
        out["next"] = "请向用户汇报交付物清单与设计要点摘要（承载能力、安全余量、关键工艺要求、遗留风险）"
    return out


def _self_check(session) -> dict:
    problems: list[str] = []
    for entry in session.ledger.entries.values():
        if entry.source.value in ("calculated", "standard_lookup") and not entry.basis:
            problems.append(f"参数 {entry.symbol} 无依据")
        if entry.status.value == "stale":
            problems.append(f"参数 {entry.symbol} 已失效")
    for record in session.calculations.values():
        if not record.source:
            problems.append(f"计算记录 {record.record_id} 未标注出处")
        if record.stale:
            problems.append(f"计算记录 {record.record_id} 已失效")
    problems += [
        f"设计输入 {i.label} 仍为未确认假设"
        for i in session.design_spec.pending_confirm()
    ]
    return {"problem_count": len(problems), "problems": problems[:20]}


class SessionSummaryArgs(BaseModel):
    pass


@register(
    "get_design_status",
    layer=ToolLayer.DELIVERY,
    args_model=SessionSummaryArgs,
    description=(
        "获取当前设计的整体状态：阶段、Gate 通过情况、设计输入完成度、"
        "台账统计、校核结论、交付物清单。用于向用户汇报进展或自我核对。"
    ),
)
async def get_design_status(ctx: ToolContext, args: SessionSummaryArgs) -> dict:
    session = ctx.session
    spec = session.design_spec
    return {
        "status": "ok",
        "mode": session.mode.value,
        "stage": session.design_stage.value,
        "family": spec.family_label or spec.family,
        "gates": {k: v.approved for k, v in session.gates.items()},
        "spec_progress": {
            "known": spec.known_count(),
            "total": len(spec.items),
            "missing_current_stage": [
                i.label for i in spec.missing_required(upto_stage=session.design_stage.value)
            ],
            "pending_confirmation": [i.label for i in spec.pending_confirm()],
        },
        "ledger": session.ledger.counts(),
        "ledger_frozen": session.ledger.is_frozen,
        "calculations": {
            "count": len(session.calculations),
            "verdicts": session.check_verdicts(),
        },
        "simulation": (
            session.simulation_report.pass_or_fail.value
            if session.simulation_report
            else "not_run"
        ),
        "geometry_file": session.geometry_file,
        "deliverables": [d.path for d in session.deliverables],
        "is_reverse_modeling": session.mode == SessionMode.REVERSE_MODELING,
    }
