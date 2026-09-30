"""CLI entry point using the new AgentLoop architecture (Inventor + ANSYS)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.model_config import load_env

from app.schemas.common import CadTarget
from app.schemas.session_state import ChatRole, DrawingArtifact, SessionState, UserIntent


def _load_env() -> None:
    load_env()


def _build_artifacts(paths: list[str]) -> list[DrawingArtifact]:
    artifacts: list[DrawingArtifact] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"图纸文件不存在: {path}")
        artifacts.append(
            DrawingArtifact(file_id=uuid4(), name=path.name, uri=str(path), ocr_ready=False)
        )
    return artifacts


def _new_session(drawings: list[str]) -> SessionState:
    return SessionState(
        session_id=uuid4(),
        user_intent=UserIntent(target_cad=CadTarget.INVENTOR),
        drawing_artifacts=_build_artifacts(drawings),
    )


def _print_chat_history(state: SessionState) -> None:
    print("\n=== 对话历史 ===")
    for msg in state.chat_history:
        role_label = "用户" if msg.role == ChatRole.USER else "助理"
        print(f"\n{role_label}:")
        print(f"  {msg.content}")
    print("================\n")


def _print_session_status(state: SessionState) -> None:
    from app.schemas.design_stage import STAGE_LABELS

    print(
        f"\n--- session: {state.session_id}"
        f" | 模式: {state.mode.value}"
        f" | 阶段: {STAGE_LABELS[state.design_stage]}"
        f" | 子agent: {state.active_agent.value} ---"
    )
    spec = state.design_spec
    if spec.items:
        print(f"设计任务书: {spec.family_label}（已确认 {spec.known_count()}/{len(spec.items)}）")
        missing = spec.missing_required(upto_stage=state.design_stage.value)
        if missing:
            print(f"  本阶段缺失: {', '.join(i.label for i in missing)}")
    if state.ledger.entries:
        counts = state.ledger.counts()
        print(
            f"参数台账: {'已冻结' if state.ledger.is_frozen else '未冻结'}"
            f"，frozen={counts['frozen']} confirmed={counts['confirmed']}"
            f" tentative={counts['tentative']} stale={counts['stale']}"
        )
    if state.calculations:
        v = state.check_verdicts()
        print(
            f"计算记录: {len(state.calculations)} 条"
            f"（通过 {v['pass']} / 不通过 {v['fail']} / 失效 {v['stale']}）"
        )
    if state.gates:
        passed = [k for k, g in state.gates.items() if g.approved]
        print(f"已通过关口: {', '.join(passed) if passed else '无'}")
    if state.pending_decision:
        print(f"待用户答复: {state.pending_decision.question}")
    if state.deliverables:
        print("交付物:")
        for d in state.deliverables:
            print(f"  - [{d.kind}] {d.path}")
    if state.geometry_file:
        print(f"几何文件: {state.geometry_file}")
    if state.simulation_report:
        sim = state.simulation_report
        print(f"仿真结论: {sim.pass_or_fail.value}")
        for item in sim.result_items:
            print(f"  - {item.name}: {item.value} {item.unit} (limit={item.limit}, pass={item.passed})")
        if sim.issues:
            print(f"  问题: {'; '.join(sim.issues)}")
    if state.last_error:
        print(f"last_error: {state.last_error}")


def _parse_paths(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


AGENT_LABELS = {
    "chief_model": "主模型（思考）",
    "assistant": "助理",
    "sketch_parser": "图纸解析 (Vision)",
    "modeling": "Inventor 建模 (mcp-cad)",
    "analysis": "ANSYS 仿真 (Math)",
    "system": "系统",
}


async def interactive_main(drawings: list[str]) -> None:
    _load_env()

    from app.agent import AgentLoop
    from app.mcp import get_manager
    from app.runtime_checks import check_mcp_servers

    manager = get_manager()
    print("正在启动 MCP 服务 (mcp-cad / ansys-workbench)...")
    await manager.start()
    for svc in check_mcp_servers():
        flag = "OK " if svc.get("connected") else "X  "
        print(f"  [{flag}] {svc['name']}: 工具数 {svc.get('tool_count', 0)}")

    try:
        current_drawings = drawings or _parse_paths(
            input("图纸路径(可空，多个用逗号分隔): ").strip()
        )
        state = _new_session(current_drawings)

        print("\n=== Inventor 建模 + ANSYS 仿真助手 (AgentLoop) ===")
        print("输入自然语言描述开始设计。")
        print("命令: /files 路径1,路径2 | /new | /quit | /exit | /history | /status")
        print("==========================================\n")

        while True:
            agent_tag = ""
            if state.active_agent.value == "modeling":
                agent_tag = "[建模]"
            elif state.active_agent.value == "analysis":
                agent_tag = "[仿真]"
            prompt = input(f"你{agent_tag}> ").strip()
            if not prompt:
                continue
            if prompt == "/quit":
                break
            if prompt == "/history":
                _print_chat_history(state)
                continue
            if prompt == "/status":
                _print_session_status(state)
                continue
            if prompt.startswith("/files "):
                current_drawings = _parse_paths(prompt.split(" ", 1)[1])
                state = _new_session(current_drawings)
                print(f"已更新图纸 -> {current_drawings}")
                continue
            if prompt == "/new":
                state = _new_session(current_drawings)
                print(f"已创建新会话 -> {state.session_id}")
                continue

            last_stream_agent: str | None = None

            def stream_callback(agent: str, delta: str) -> None:
                nonlocal last_stream_agent
                if not delta:
                    return
                if agent != last_stream_agent:
                    title = AGENT_LABELS.get(agent, agent)
                    print(f"\n\n--- {title} ---\n", end="", flush=True)
                    last_stream_agent = agent
                print(delta, end="", flush=True)

            agent_loop = AgentLoop(session=state)
            try:
                result = await agent_loop.run(prompt, stream_callback=stream_callback)
                state = result.session
            except Exception as exc:
                print(f"\n\n[错误] {exc}")
                state.last_error = str(exc)
                continue

            if getattr(result, "noop", False):
                continue
            print("\n")
            print(f"助理: {result.content}")
            if result.tool_calls_made:
                print(f"  [工具调用: {', '.join(result.tool_calls_made)}]")
    finally:
        print("\n正在关闭 MCP 服务...")
        await manager.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventor 建模 + ANSYS 仿真助手 (AgentLoop)")
    parser.add_argument("--drawing", action="append", default=[], help="图纸路径，可重复传入")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(interactive_main(args.drawing))


if __name__ == "__main__":
    main()
