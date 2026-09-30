"""One-shot: re-export STEP from Inventor (if open) and run compressive static analysis."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

SESSION_ID = "c53feceb-5fe1-4339-b0ea-98186a98c42a"
EXPORT_DIR = Path(os.getenv("MCPCAD_EXPORT_DIR", "D:/Inventor_Export"))
STEP_PATH = EXPORT_DIR / f"{SESSION_ID}.stp"

ANALYSIS_INTENT = (
    "对阶梯轴进行静力结构抗压强度分析。"
    "材料：45号钢（调质态），弹性模量210 GPa，泊松比0.3，屈服强度355 MPa，密度7850 kg/m³。"
    "边界条件：左端面固定约束（限制全部平移自由度）；"
    "右端面施加轴向压应力 100 MPa（Pressure 载荷，方向沿轴向内压）。"
    "分析目标：提取最大等效应力（von Mises）与最大轴向压缩应力，"
    "与45号钢屈服强度355 MPa对比，判断抗压强度是否满足要求；"
    "重点关注轴肩、退刀槽等应力集中区域。"
)


async def main() -> int:
    from app.agent.analysis_agent import AnalysisAgent
    from app.mcp import MCPCAD, get_manager

    manager = get_manager()
    print("启动 MCP 服务...")
    await manager.start()

    cad_ok = manager.is_connected(MCPCAD)
    ansys_ok = manager.is_connected("ansys-workbench")
    print(f"  mcp-cad: {'OK' if cad_ok else 'FAIL'}")
    print(f"  ansys-workbench: {'OK' if ansys_ok else 'FAIL'}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not STEP_PATH.exists():
        if not cad_ok:
            print(f"STEP 不存在且 mcp-cad 未连接: {STEP_PATH}")
            return 1
        print(f"尝试从 Inventor 重新导出: {STEP_PATH}")
        health = await manager.call(MCPCAD, "inventor_health", {})
        print(f"  inventor_health: success={health.success} data={health.data}")
        export = await manager.call(MCPCAD, "export_step", {"path": str(STEP_PATH)})
        print(f"  export_step: success={export.success} error={export.error} data={export.data}")
        if not export.success or not STEP_PATH.exists():
            print("导出失败。请确认 Inventor 中阶梯轴模型仍打开，或在 CLI 中重新 build_model。")
            return 1
    else:
        print(f"STEP 已存在: {STEP_PATH} ({STEP_PATH.stat().st_size} bytes)")

    if not ansys_ok:
        print("ansys-workbench 未连接，无法仿真")
        return 1

    print("\n开始 ANSYS 静力抗压分析...")
    agent = AnalysisAgent()

    def _stream(ev) -> None:
        if ev.data:
            print(ev.data, end="", flush=True)

    result = await agent.run(
        analysis_intent=ANALYSIS_INTENT,
        geometry_file=str(STEP_PATH),
        analysis_type="static_structural",
        session_id=SESSION_ID,
        stream_callback=_stream,
    )

    print("\n--- 仿真结果 ---")
    print(f"success: {result.success}")
    print(f"status: {result.status}")
    print(f"error: {result.error}")
    print(f"iterations: {result.iterations}")
    print(f"tool_calls: {result.tool_calls}")
    if result.summary:
        print(f"summary:\n{result.summary}")
    if result.result_data:
        import json
        print(f"result_data:\n{json.dumps(result.result_data, ensure_ascii=False, indent=2)}")

    await manager.stop()
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
