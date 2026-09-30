"""主设计模型的上下文组装。"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.design_stage import (
    SCOPE_LABELS,
    STAGE_LABELS,
    DesignScope,
    stage_index,
    stage_order,
)
from app.schemas.session_state import SessionState

from ..prompt import USER_MESSAGE_WITH_DRAWINGS_TEMPLATE, build_main_system_prompt


class SessionContext:
    """组装系统提示词与状态快照。"""

    def __init__(self, session: SessionState):
        self.session = session

    # ---- 系统提示词 ----

    def build_system_prompt(self) -> str:
        static_part = build_main_system_prompt(self.session)
        snapshot = self.build_state_snapshot()
        if snapshot:
            return f"{static_part}\n\n{'=' * 30} 当前设计状态 {'=' * 30}\n\n{snapshot}"
        return static_part

    def build_state_snapshot(self) -> str:
        blocks = [
            self._block_stage(),
            self._block_pending_decision(),
            self._block_spec(),
            self._block_scheme(),
            self._block_ledger(),
            self._block_calculations(),
            self._block_geometry(),
            self._block_assembly(),
            self._block_verification(),
            self._block_deliverables(),
            self._block_drawings(),
            self._block_error(),
        ]
        return "\n\n".join(b for b in blocks if b)

    # ---- 各状态块 ----

    def _block_stage(self) -> str:
        session = self.session
        stage = session.design_stage
        order = stage_order(session.design_scope)
        idx = stage_index(stage, session.design_scope) + 1
        total = len(order)
        lines = [
            f"【当前设计阶段】{STAGE_LABELS[stage]}（第 {idx}/{total} 阶段，"
            f"stage={stage.value}）",
            f"  工作模式：{'正向设计' if session.mode.value == 'design' else '逆向建模'}",
            f"  设计范围：{SCOPE_LABELS[session.design_scope]}"
            + (
                "（⛔ 尚未判定，请尽早 set_design_scope）"
                if session.design_scope == DesignScope.UNDECIDED
                else ""
            ),
        ]
        if session.gates:
            passed = [k for k, v in session.gates.items() if v.approved]
            lines.append(f"  已通过关口：{', '.join(passed) if passed else '无'}")
        else:
            lines.append("  已通过关口：无")
        return "\n".join(lines)

    def _block_pending_decision(self) -> str:
        decision = self.session.pending_decision
        if decision is None:
            return ""
        return (
            "【待用户答复的问题】（用户的下一条消息即为对此的答复）\n"
            f"  {decision.render_for_prompt()}"
        )

    def _block_spec(self) -> str:
        spec = self.session.design_spec
        if not spec.items:
            return "【设计任务书】尚未建立。请先 list_design_families 确认零件族，再 start_design"

        missing_now = spec.missing_required(upto_stage=self.session.design_stage.value)
        missing_later = [
            i
            for i in spec.missing_required()
            if i not in missing_now
        ]
        pending = spec.pending_confirm()

        lines = [
            f"【设计任务书】{spec.family_label or spec.family}"
            f"（已确认 {spec.known_count()}/{len(spec.items)} 项）",
            spec.render_snapshot(),
        ]
        if missing_now:
            lines.append(
                "  ⛔ 本阶段仍缺必填项："
                + "；".join(f"{i.label}（{i.key}）" for i in missing_now)
            )
        if missing_later:
            lines.append(
                "  ○ 后续阶段需要："
                + "；".join(f"{i.label}@{i.needed_by_stage}" for i in missing_later)
            )
        if pending:
            lines.append(
                "  ⚠ 待用户确认的工程假设："
                + "；".join(f"{i.label}={i.render_value()}" for i in pending)
            )
        return "\n".join(lines)

    def _block_scheme(self) -> str:
        alts = self.session.alternatives
        if not alts:
            return ""
        lines = ["【备选方案】"]
        for idx, alt in enumerate(alts):
            mark = " ✓已选定" if alt.selected else ""
            lines.append(f"  {idx}. {alt.name}{mark} — {alt.summary or alt.structure}")
        return "\n".join(lines)

    def _block_ledger(self) -> str:
        ledger = self.session.ledger
        if not ledger.entries:
            return "【参数台账】空。设计参数须经 commit_parameter 落账后才能用于建模"

        counts = ledger.counts()
        state = "已冻结" if ledger.is_frozen else "未冻结"
        lines = [
            f"【参数台账】{state}；"
            f"frozen {counts['frozen']} / confirmed {counts['confirmed']} / "
            f"tentative {counts['tentative']} / stale {counts['stale']}",
            ledger.render_snapshot(),
        ]
        stale = ledger.stale()
        if stale:
            lines.append(
                "  ⛔ 已失效参数（必须重算）："
                + "；".join(f"{e.symbol}（{e.stale_reason}）" for e in stale)
            )
        assumed = ledger.assumed()
        if assumed:
            lines.append(
                "  ⚠ 工程假设参数：" + "；".join(e.symbol for e in assumed)
            )
        return "\n".join(lines)

    def _block_calculations(self) -> str:
        calcs = self.session.calculations
        if not calcs:
            return (
                "【计算记录】无。任何设计数值都必须先经 solve_formula / run_calculation "
                "产生记录，不得直接报数"
            )
        verdicts = self.session.check_verdicts()
        lines = [
            f"【计算记录索引】共 {len(calcs)} 条"
            f"（校核通过 {verdicts['pass']} / 不通过 {verdicts['fail']} / "
            f"非校核 {verdicts['n/a']} / 已失效 {verdicts['stale']}）"
            "  — 需要全文时用 get_calculation_record 查",
        ]
        ordered = sorted(
            calcs.values(),
            key=lambda r: int(r.record_id.split("#")[-1])
            if r.record_id.split("#")[-1].isdigit()
            else 0,
        )
        for record in ordered[-18:]:
            lines.append(f"  {record.render_line()}")
        if len(ordered) > 18:
            lines.insert(1, f"  （仅列出最近 18 条，共 {len(ordered)} 条）")

        failed = self.session.failed_checks()
        if failed:
            lines.append(
                "  ⛔ 未通过的校核："
                + "；".join(f"{r.record_id} {r.title}" for r in failed)
            )
        return "\n".join(lines)

    def _block_geometry(self) -> str:
        session = self.session
        if not session.geometry_file and session.modeling_contract is None:
            return ""
        lines = ["【几何表达】"]
        if session.modeling_contract is not None:
            contract = session.modeling_contract
            lines.append(
                f"  契约：{contract.part_name}（{contract.part_type}），"
                f"{len(contract.body_segments)} 段 / "
                f"{len(contract.local_features)} 个局部特征"
            )
        if session.geometry_file:
            lines.append(f"  几何文件：{session.geometry_file}")
        return "\n".join(lines)

    def _block_assembly(self) -> str:
        session = self.session
        if not session.is_assembly_scope:
            return ""

        parts = session.part_builds
        handoff = session.assembly_handoff
        lines = ["【装配体进度】"]

        if not parts:
            lines.append(
                "  零件清单：尚未登记。参数冻结后请先 declare_assembly_parts 列出"
                "需自己建模的零件（标准件不列入）"
            )
        else:
            built = session.built_parts()
            lines.append(f"  零件清单：共 {len(parts)} 个，已建模 {len(built)} 个")
            for part in parts:
                mark = "✓" if part.is_built else "○"
                role = f"（{part.role}）" if part.role else ""
                tail = f" → {part.geometry_file}" if part.geometry_file else ""
                lines.append(
                    f"    {mark} {part.part_name}{role} [{part.status.value}]{tail}"
                )
            remaining = [p.part_name for p in session.unbuilt_parts()]
            if remaining:
                lines.append(f"  ○ 待建模：{'；'.join(remaining)}")

        if handoff.submitted:
            lines.append(
                f"  ✓ 装配已交接（{handoff.source_kind}）：{handoff.step_file}"
            )
            if handoff.iam_file:
                lines.append(f"    源装配体：{handoff.iam_file}")
            if handoff.notes:
                lines.append(f"    用户说明：{'；'.join(handoff.notes)}")
            lines.append("  → 可对该装配体几何运行装配级 run_simulation")
        elif session.all_parts_built():
            lines.append(
                "  ⛔ 全部零件已建完但装配尚未交接。"
                "请勿询问是否进入仿真——应要求用户在 Inventor 中手工装配、保存为 .iam，"
                "并提交 .iam 路径（系统会导出 STP）或用户自行导出的 .stp 路径，"
                "然后调用 submit_assembly_geometry"
            )
        else:
            lines.append(
                "  ○ 装配未交接。零件全部建完后才要求用户装配；"
                "装配级仿真必须基于用户提交的装配体几何"
            )
        return "\n".join(lines)

    def _block_verification(self) -> str:
        report = self.session.simulation_report
        if report is None:
            return ""
        lines = [f"【有限元校核】结论：{report.pass_or_fail.value}"]
        for item in report.result_items[:5]:
            lines.append(
                f"  {item.name}: {item.value} {item.unit}"
                f"（限值 {item.limit}，{'满足' if item.passed else '不满足'}）"
            )
        if report.issues:
            lines.append(f"  问题：{'；'.join(report.issues[:3])}")
        if report.recommended_adjustments:
            lines.append(f"  建议调整：{'；'.join(report.recommended_adjustments[:3])}")
        return "\n".join(lines)

    def _block_deliverables(self) -> str:
        items = self.session.deliverables
        if not items:
            return ""
        lines = ["【已生成交付物】"]
        for d in items[-8:]:
            lines.append(f"  [{d.kind}] {d.title} → {d.path}")
        return "\n".join(lines)

    def _block_drawings(self) -> str:
        session = self.session
        if not session.drawing_artifacts:
            return ""
        names = json.dumps(
            [{"name": a.name, "uri": a.uri} for a in session.drawing_artifacts],
            ensure_ascii=False,
        )
        lines = [f"【已上传图纸】{names}"]
        drawing = session.semantic_facts.get("drawing")
        if isinstance(drawing, dict):
            summary = drawing.get("semantic_summary")
            if summary:
                lines.append(f"  解析摘要：{str(summary)[:300]}")
            check = drawing.get("dimension_chain_check")
            if isinstance(check, dict) and check.get("consistent") is False:
                lines.append(f"  ⚠ 尺寸链不自洽：{check.get('note', '')}")
            questions = drawing.get("open_questions") or []
            if questions:
                lines.append(f"  待确认：{'；'.join(str(q) for q in questions[:3])}")
        return "\n".join(lines)

    def _block_error(self) -> str:
        if not self.session.last_error:
            return ""
        return f"【上次错误】\n  {self.session.last_error[:300]}"

    # ---- 用户消息 ----

    def build_user_message(self, user_input: str) -> str:
        if self.session.drawing_artifacts:
            names = ", ".join(a.name for a in self.session.drawing_artifacts)
            return USER_MESSAGE_WITH_DRAWINGS_TEMPLATE.format(
                user_input=user_input, artifact_names=names
            )
        return user_input

    def get_drawing_uris(self) -> list[str]:
        return [a.uri for a in self.session.drawing_artifacts]

    def update_semantic_facts(self, key: str, value: Any) -> None:
        self.session.semantic_facts[key] = value

    def to_dict(self) -> dict[str, Any]:
        session = self.session
        return {
            "session_id": str(session.session_id),
            "mode": session.mode.value,
            "design_stage": session.design_stage.value,
            "gates_passed": [k for k, v in session.gates.items() if v.approved],
            "spec_known": session.design_spec.known_count(),
            "spec_total": len(session.design_spec.items),
            "ledger_counts": session.ledger.counts(),
            "calculation_count": len(session.calculations),
            "has_geometry": bool(session.geometry_file),
            "deliverable_count": len(session.deliverables),
        }
