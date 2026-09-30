"""设计系统冒烟测试：不调用 LLM，直接驱动工具链走完一段设计流程。

覆盖：知识库加载、工具注册与 schema 生成、公式求解、标准圆整、台账溯源校验、
变更失效传播、门控拒绝、中断机制、交付物渲染。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.tools import ToolContext, ToolInterrupt, build_openai_tools, dispatch
from app.schemas.session_state import SessionState

PASS, FAIL = "  [OK]", "  [!!]"
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"{PASS} {label}")
    else:
        print(f"{FAIL} {label} {detail}")
        failures.append(label)


async def call(ctx: ToolContext, tool: str, /, **kwargs) -> dict:
    return await dispatch(tool, kwargs, ctx)


async def main() -> int:
    session = SessionState(session_id=uuid4())
    ctx = ToolContext(session=session)

    print("\n=== 1. 工具注册表 ===")
    tools = build_openai_tools()
    names = sorted(t["function"]["name"] for t in tools)
    check(f"注册 {len(tools)} 个工具", len(tools) >= 20, str(names))
    check(
        "schema 已展平（无 $ref/$defs）",
        "$ref" not in str(tools) and "$defs" not in str(tools),
    )
    sf = next(t for t in tools if t["function"]["name"] == "solve_formula")
    check(
        "solve_formula 参数含 inputs",
        "inputs" in sf["function"]["parameters"]["properties"],
    )

    print("\n=== 2. 设计输入收敛 ===")
    r = await call(ctx, "list_design_families")
    check("列出零件族", r["status"] == "ok" and r["families"], str(r)[:150])

    r = await call(ctx, "start_design", family="gearbox_single_stage", title="冒烟测试减速器")
    check("建立设计任务书", r["status"] == "ok" and len(r["all_items"]) > 15)
    check("返回本阶段缺失项", len(r["missing_now"]) > 0)

    r = await call(
        ctx,
        "update_design_spec",
        entries=[
            {"key": "transmitted_power", "value": "4 kW", "status": "user_given"},
            {"key": "input_speed", "value": "1440 r/min", "status": "user_given"},
            {"key": "total_ratio", "value": "3.2", "status": "user_given"},
            {"key": "load_character", "value": "平稳", "status": "user_given"},
            {"key": "daily_hours", "value": "16 hour", "status": "user_given"},
            {"key": "service_years", "value": "10", "status": "user_given"},
            {
                "key": "accuracy_grade",
                "value": "8级",
                "status": "assumed_pending_confirm",
                "rationale": "一般传动惯用值，圆周速度不高",
            },
        ],
        source="冒烟测试",
    )
    check("记录设计输入", r["status"] == "ok" and len(r["updated"]) == 7)
    check("识别待确认假设", len(r["pending_confirmation"]) == 1)

    r = await call(
        ctx,
        "update_design_spec",
        entries=[
            {"key": "accuracy_grade", "value": "8级", "status": "assumed_pending_confirm"}
        ],
    )
    check("假设无理由被拒", r["status"] == "refused", str(r)[:120])

    print("\n=== 3. 门控拒绝 ===")
    r = await call(ctx, "set_design_stage", stage="detail_calculation")
    check("未过 Gate1 不得进入详细计算", r["status"] == "refused", str(r)[:120])

    r = await call(
        ctx,
        "plan_modeling_contract",
        part_name="test",
        part_type="shaft",
        coordinate_system={"axis": "X"},
        body_segments=[],
    )
    check("未冻结台账不得建模契约", r["status"] == "refused", str(r)[:120])

    print("\n=== 4. 中断机制 ===")
    interrupted = False
    try:
        await dispatch(
            "request_user_decision",
            {
                "question": "齿轮材料方案？",
                "kind": "scheme_choice",
                "options": [
                    {"label": "软齿面 45钢调质", "pros": ["成本低"], "cons": ["承载低"]},
                    {"label": "硬齿面 20CrMnTi", "pros": ["承载高"], "cons": ["需磨齿"]},
                ],
                "recommended_index": 0,
                "reasoning": "载荷平稳、功率不大",
            },
            ctx,
        )
    except ToolInterrupt as exc:
        interrupted = True
        check("提问触发中断", True)
        check("待决问题可渲染", "软齿面" in exc.decision.render_for_user())
    check("request_user_decision 抛出 ToolInterrupt", interrupted)

    r = await dispatch(
        "request_user_decision",
        {"question": "选哪个？", "kind": "scheme_choice", "options": []},
        ctx,
    )
    check("方案选择缺选项被拒", r["status"] == "refused")

    print("\n=== 5. 知识层 ===")
    r = await call(ctx, "search_formula", query="齿面接触疲劳强度设计")
    check("检索公式", r["status"] == "ok" and r["count"] > 0)
    fid = r["formulas"][0]["formula_id"]

    r = await call(ctx, "search_formula", formula_id="gear_contact_design_d1")
    check("取公式全文", "Z_E" in r["formula"] and "GB" in r["formula"] or "机械设计" in r["formula"])

    r = await call(ctx, "lookup_material", grade="45", heat_treatment="调质")
    check("查材料", r["status"] == "ok" and r["materials"][0]["properties"]["sigma_Hlim"]["value"] == 600)

    r = await call(ctx, "lookup_standard_part", family_id="key", shaft_diameter=35.0)
    check("按轴径选键", r["status"] == "ok" and r["candidates"][0]["b"] == 10)

    r = await call(ctx, "lookup_standard_series", series_id="gb1357_modulus", value=1.99)
    check("模数圆整到 2.0", r["rounded_value"] == 2.0, str(r)[:120])

    print("\n=== 6. 计算与台账 ===")
    r = await call(
        ctx,
        "solve_formula",
        formula_id="shaft_torque_from_power",
        inputs={"P": {"value": 4.0, "unit": "kW"}, "n": {"value": 1440.0, "unit": "r/min"}},
        title="输入轴转矩",
    )
    check("求解转矩", r["status"] == "ok" and abs(r["result"]["T"]["value"] - 26527.8) < 5, str(r)[:150])
    calc_T = r["record_id"]

    r = await call(
        ctx,
        "commit_parameter",
        symbol="T_1",
        name="小齿轮转矩",
        value={"value": 26527.8, "unit": "N*mm"},
        source="calculated",
        basis=[calc_T],
        group="总体",
    )
    check("有据参数落账", r["status"] == "ok")

    r = await call(
        ctx,
        "commit_parameter",
        symbol="d_bogus",
        value={"value": 30.0, "unit": "mm"},
        source="calculated",
        basis=[],
    )
    check("无据参数被拒（铁律二）", r["status"] == "refused", str(r)[:150])

    r = await call(
        ctx,
        "commit_parameter",
        symbol="d_bogus",
        value={"value": 30.0, "unit": "mm"},
        source="calculated",
        basis=["calc#999"],
    )
    check("引用不存在的计算记录被拒", r["status"] == "refused", str(r)[:150])

    r = await call(
        ctx,
        "solve_formula",
        formula_id="gear_contact_design_d1",
        inputs={
            "T_1": {"value": 26527.8, "unit": "N*mm"},
            "phi_d": {"value": 1.0, "unit": ""},
            "u": {"value": 3.2, "unit": ""},
            "sigma_HP": {"value": 550.0, "unit": "MPa"},
        },
        title="按接触强度设计小齿轮分度圆直径",
        depends_on=["T_1"],
    )
    check("接触强度设计求解", r["status"] == "ok" and 35 < r["result"]["d_1t"]["value"] < 45, str(r)[:150])
    calc_d1 = r["record_id"]

    r = await call(
        ctx,
        "solve_formula",
        formula_id="gear_contact_design_d1",
        inputs={"T_1": {"value": 26527.8, "unit": "kW"}, "phi_d": {"value": 1.0},
                "u": {"value": 3.2}, "sigma_HP": {"value": 550.0, "unit": "MPa"}},
    )
    check("量纲错误被拒（铁律三）", r["status"] == "refused", str(r)[:150])

    r = await call(
        ctx,
        "solve_formula",
        formula_id="gear_bending_check",
        inputs={
            "K_F": {"value": 1.5}, "T_1": {"value": 26527.8, "unit": "N*mm"},
            "Y_Fa": {"value": 2.65}, "Y_Sa": {"value": 1.58},
            "b": {"value": 48, "unit": "mm"}, "d_1": {"value": 48, "unit": "mm"},
            "m": {"value": 2.0, "unit": "mm"}, "sigma_FP": {"value": 150.0, "unit": "MPa"},
        },
        title="齿根弯曲疲劳强度校核",
        depends_on=["T_1", calc_d1],
    )
    check("校核判据自动判定", r["verdict"] == "pass" and r["margin_percent"] is not None, str(r)[:150])
    calc_bend = r["record_id"]

    print("\n=== 7. 沙箱计算 ===")
    r = await call(
        ctx,
        "run_calculation",
        title="深沟球轴承寿命",
        script="L10h = 1e6/(60*n) * (Cr/P)**3\noutputs['L10h'] = L10h",
        inputs={"n": {"value": 1440.0, "unit": "r/min"}, "Cr": {"value": 19500.0, "unit": "N"},
                "P": {"value": 1450.0, "unit": "N"}},
        expected_outputs=["L10h"],
        output_units={"L10h": "hour"},
        source="GB/T 6391-2010",
    )
    check("沙箱计算", r["status"] == "ok" and r["result"]["L10h"]["value"] > 20000, str(r)[:150])

    r = await call(ctx, "run_calculation", title="越界", script="import os\noutputs['x']=1")
    check("沙箱拦截 import", r["status"] == "refused")

    print("\n=== 8. 变更失效传播 ===")
    r = await call(
        ctx,
        "commit_parameter",
        symbol="T_1",
        value={"value": 30000.0, "unit": "N*mm"},
        source="calculated",
        basis=[calc_T],
    )
    check("参数变更被记录", r["status"] == "ok" and r["revision"] == 2)
    check(
        "依赖的计算被标记失效",
        calc_bend in r.get("invalidated", {}).get("stale_calculations", []),
        str(r.get("invalidated")),
    )

    r = await call(ctx, "freeze_parameters", user_statement="同意冻结")
    check("有失效项不得冻结", r["status"] == "refused", str(r)[:150])

    print("\n=== 9. 冻结与建模门控 ===")
    for rid in list(session.calculations):
        session.calculations[rid].stale = False
    r = await call(ctx, "freeze_parameters", user_statement="台账已核对，同意冻结", confirm_assumptions=True)
    check("冻结成功", r["status"] == "ok" and r["frozen_count"] >= 1, str(r)[:150])
    check("Gate2 已通过", session.gate_passed("gate2_parameters_frozen"))

    r = await call(
        ctx,
        "plan_modeling_contract",
        part_name="input_shaft",
        part_type="shaft",
        coordinate_system={"axis": "X", "origin": "left_end"},
        body_segments=[
            {
                "name": "journal",
                "shape": "cylinder",
                "axis_start_cm": 0.0,
                "axis_end_cm": 3.0,
                "sketch_plane": "YZ@X=0.0",
                "feature_op": "revolve",
                "diameter_cm": 3.5,
                "from_parameters": ["nonexistent_symbol"],
            }
        ],
    )
    check("引用台账外参数被拒", r["status"] == "refused", str(r)[:150])

    r = await call(
        ctx,
        "plan_modeling_contract",
        part_name="input_shaft",
        part_type="shaft",
        coordinate_system={"axis": "X", "origin": "left_end"},
        body_segments=[
            {
                "name": "journal",
                "shape": "cylinder",
                "axis_start_cm": 0.0,
                "axis_end_cm": 3.0,
                "sketch_plane": "YZ@X=0.0",
                "feature_op": "revolve",
                "diameter_cm": 3.5,
                "from_parameters": ["T_1"],
            }
        ],
    )
    check("溯源完整的契约通过", r["status"] == "ok", str(r)[:200])

    print("\n=== 10. 交付物 ===")
    r = await call(ctx, "generate_design_report", export_docx=True)
    check("Gate3 未过不得出正式文档", r["status"] == "refused", str(r)[:150])

    r = await call(ctx, "generate_design_report", force=True, export_docx=True)
    check("草稿生成成功", r["status"] == "ok" and r["is_draft"], str(r)[:200])
    if r.get("status") == "ok":
        for f in r["files"]:
            exists = Path(f["path"]).is_file()
            check(f"文件已写出 {f['kind']}", exists, f["path"])
        md = next((f for f in r["files"] if f["kind"] == "design_report"), None)
        if md:
            text = Path(md["path"]).read_text(encoding="utf-8")
            check("说明书含参数台账章节", "设计参数汇总" in text)
            check("说明书含溯源自检", "溯源自检" in text)
            check("说明书标注草稿", "未定稿草稿" in text)

    r = await call(ctx, "get_design_status")
    check("状态汇总可用", r["status"] == "ok" and r["ledger_frozen"])

    print("\n=== 11. 上下文快照 ===")
    from app.agent.context.session_context import SessionContext

    snapshot = SessionContext(session).build_system_prompt()
    check("提示词含铁律", "铁律一" in snapshot)
    check("提示词含阶段手册", "当前设计阶段" in snapshot)
    check("提示词含台账快照", "参数台账" in snapshot)
    check("提示词规模合理（<26k 字符）", len(snapshot) < 26000, f"{len(snapshot)} 字符")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"失败 {len(failures)} 项：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
