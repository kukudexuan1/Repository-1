"""设计范围（单零件 / 装配体）与装配交接关口的行为测试。

核心不变量：装配体的装配由用户手工完成，系统不得自行装配，
也不得在装配未交接时用零件几何冒充装配体运行装配级 CAE。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.agent.tools.express_tools import (
    RunSimulationArgs,
    SubmitAssemblyArgs,
    run_simulation,
    submit_assembly_geometry,
)
from app.agent.tools.registry import ToolRefusal
from app.schemas.design_stage import (
    DesignScope,
    DesignStage,
    Gate,
    next_stage,
    stage_order,
)
from app.schemas.session_state import PartBuild, PartBuildStatus, SessionState


class _Ctx:
    """最小 ToolContext 替身：这些用例只走门控分支，不触达子 Agent。"""

    def __init__(self, session: SessionState) -> None:
        self.session = session
        self.extras: dict = {}

    def say(self, *_args, **_kwargs) -> None:
        pass


@pytest.fixture()
def step_file(tmp_path: Path) -> str:
    path = tmp_path / "geom.stp"
    path.write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return str(path)


def _assembly_session(step: str) -> SessionState:
    session = SessionState(session_id=uuid4())
    session.design_scope = DesignScope.ASSEMBLY
    session.design_stage = DesignStage.GEOMETRY
    session.part_builds = [
        PartBuild(part_name="shaft", status=PartBuildStatus.BUILT, geometry_file=step),
        PartBuild(part_name="gear", status=PartBuildStatus.BUILT, geometry_file=step),
    ]
    session.geometry_file = step
    return session


def test_stage_order_excludes_handoff_for_single_part() -> None:
    single = stage_order(DesignScope.SINGLE_PART)
    assembly = stage_order(DesignScope.ASSEMBLY)

    assert DesignStage.ASSEMBLY_HANDOFF not in single
    assert DesignStage.ASSEMBLY_HANDOFF in assembly


def test_geometry_advances_to_handoff_only_for_assembly() -> None:
    assert (
        next_stage(DesignStage.GEOMETRY, DesignScope.ASSEMBLY)
        is DesignStage.ASSEMBLY_HANDOFF
    )
    assert (
        next_stage(DesignStage.GEOMETRY, DesignScope.SINGLE_PART)
        is DesignStage.VERIFICATION
    )
@pytest.mark.asyncio
async def test_assembly_simulation_refused_before_handoff(step_file: str) -> None:
    session = _assembly_session(step_file)

    with pytest.raises(ToolRefusal, match="装配体尚未交接"):
        await run_simulation(
            _Ctx(session), RunSimulationArgs(analysis_intent="整体承载")
        )


@pytest.mark.asyncio
async def test_handoff_accepts_user_exported_step(step_file: str) -> None:
    session = _assembly_session(step_file)

    result = await submit_assembly_geometry(
        _Ctx(session),
        SubmitAssemblyArgs(path=step_file, user_statement="已在 Inventor 中装好并导出"),
    )

    assert result["source_kind"] == "stp"
    assert session.gate_passed(Gate.ASSEMBLY_SUBMITTED)
    assert session.design_stage is DesignStage.VERIFICATION
    assert session.simulation_geometry() == step_file
    assert session.assembly_handoff.step_hash


@pytest.mark.asyncio
async def test_handoff_refused_for_single_part_scope(step_file: str) -> None:
    session = SessionState(session_id=uuid4())
    session.design_scope = DesignScope.SINGLE_PART

    with pytest.raises(ToolRefusal, match="无需装配交接"):
        await submit_assembly_geometry(
            _Ctx(session),
            SubmitAssemblyArgs(path=step_file, user_statement="装好了"),
        )


@pytest.mark.asyncio
async def test_handoff_requires_explicit_user_statement(step_file: str) -> None:
    session = _assembly_session(step_file)

    with pytest.raises(ToolRefusal, match="用户确认"):
        await submit_assembly_geometry(
            _Ctx(session), SubmitAssemblyArgs(path=step_file, user_statement="   ")
        )
@pytest.mark.asyncio
async def test_tampered_assembly_geometry_invalidates_handoff(step_file: str) -> None:
    session = _assembly_session(step_file)
    await submit_assembly_geometry(
        _Ctx(session),
        SubmitAssemblyArgs(path=step_file, user_statement="装好了"),
    )

    with open(step_file, "a", encoding="utf-8") as fh:
        fh.write("TAMPERED\n")

    with pytest.raises(ToolRefusal, match="交接证据已失效"):
        await run_simulation(
            _Ctx(session), RunSimulationArgs(analysis_intent="整体承载")
        )


@pytest.mark.asyncio
async def test_foreign_geometry_refused_for_assembly_simulation(
    step_file: str, tmp_path: Path
) -> None:
    session = _assembly_session(step_file)
    await submit_assembly_geometry(
        _Ctx(session),
        SubmitAssemblyArgs(path=step_file, user_statement="装好了"),
    )

    other = tmp_path / "elsewhere.stp"
    other.write_text("ISO-10303-21;\n", encoding="utf-8")

    with pytest.raises(ToolRefusal, match="未经装配交接"):
        await run_simulation(
            _Ctx(session),
            RunSimulationArgs(analysis_intent="整体承载", geometry_file=str(other)),
        )


@pytest.mark.asyncio
async def test_handoff_rejects_unsupported_file_type(tmp_path: Path) -> None:
    bad = tmp_path / "model.ipt"
    bad.write_text("x", encoding="utf-8")
    session = _assembly_session(str(bad))

    with pytest.raises(ToolRefusal, match="不支持的文件类型"):
        await submit_assembly_geometry(
            _Ctx(session), SubmitAssemblyArgs(path=str(bad), user_statement="装好了")
        )


def test_part_registry_tracks_build_progress(step_file: str) -> None:
    session = _assembly_session(step_file)
    session.part_builds[1].status = PartBuildStatus.PLANNED
    session.part_builds[1].geometry_file = ""

    assert not session.all_parts_built()
    assert [p.part_name for p in session.unbuilt_parts()] == ["gear"]

    session.part_builds[1].status = PartBuildStatus.BUILT
    session.part_builds[1].geometry_file = step_file

    assert session.all_parts_built()
    assert len(session.built_parts()) == 2
