from __future__ import annotations

import asyncio

import pytest

from app.agent.modeling_agent import ModelingAgent
from app.agent.prompt import build_modeling_system_prompt
from app.agent.qwen_client import ModelResponse, ToolCall
from app.mcp.result import ToolResult
from app.schemas.modeling_contract import BodySegment, LocalFeature, ModelingContract
from app.schemas.modeling_plan import GeometryVerificationReport, VerificationStatus
from app.services.modeling.compiler import compile_contract
from app.services.modeling.conflicts import inspect_spatial_result
from app.services.modeling.contract_validator import validate_contract
from app.services.modeling.migration import migrate_v1_contract
from app.services.modeling.verifier import verify_geometry


def _shaft() -> ModelingContract:
    return ModelingContract(
        session_id="test",
        part_name="stepped_shaft",
        part_type="shaft",
        body_segments=[
            BodySegment(name="left", axis_start_cm=0, axis_end_cm=2, diameter_cm=2),
            BodySegment(name="seat", axis_start_cm=2, axis_end_cm=5, diameter_cm=3),
        ],
        local_features=[
            LocalFeature(
                name="keyway",
                feature_type="keyway",
                target_segment="seat",
                axis_start_cm=2,
                axis_end_cm=5,
                dimensions_cm={"length": 3, "width": 0.5, "depth": 0.2},
            )
        ],
    )


def test_contract_compiles_to_non_operational_expectations() -> None:
    contract = _shaft()
    assert validate_contract(contract).valid

    expectation = compile_contract(contract)

    assert expectation.plan_version == "4.0-expectations"
    assert not hasattr(expectation, "steps")
    assert not hasattr(expectation, "allowed_tools")
    assert expectation.expected_bbox_cm == {"x": 5, "y": 3, "z": 3}
    assert [feature.name for feature in expectation.features] == ["keyway"]


def test_contract_does_not_reject_agent_supported_geometry() -> None:
    contract = ModelingContract(
        session_id="broader",
        part_name="broader",
        coordinate_system={"origin_coords": [1, 0, 0]},
        body_segments=[
            BodySegment(name="a", shape="box", axis_start_cm=0, axis_end_cm=1, width_cm=2, height_cm=1),
            BodySegment(name="b", axis_start_cm=2, axis_end_cm=3, diameter_cm=1),
        ],
        local_features=[
            LocalFeature(
                name="hole",
                feature_type="hole",
                target_segment="a",
                axis_start_cm=0.2,
                axis_end_cm=0.8,
                dimensions_cm={"diameter": 0.2},
            )
        ],
    )

    report = validate_contract(contract)
    codes = {issue.code for issue in report.issues}

    assert report.valid
    assert {"coordinate.nonzero_origin", "segment.gap"} <= codes
    assert not any(code.startswith("compiler.") for code in codes)


def test_v1_migration_rejects_conflicting_spatial_fields() -> None:
    raw = {
        "session_id": "legacy",
        "part_name": "shaft",
        "coordinate_system": {"axis": "X", "radial_up": "+Z", "radial_side": "+Y"},
        "body_segments": [
            {"name": "shaft", "axis_start_cm": 0, "axis_end_cm": 5, "diameter_cm": 2}
        ],
        "local_features": [
            {
                "name": "keyway",
                "feature_type": "keyway",
                "target_segment": "shaft",
                "sketch_plane": "XZ@Y=1",
                "cut_direction": "+Z",
                "axis_start_cm": 1,
                "axis_end_cm": 4,
                "angular_position": "top(+Z)",
                "dimensions_cm": {"length": 3, "width": 0.5, "depth": 0.2},
            }
        ],
    }

    contract, report = migrate_v1_contract(raw)

    assert contract is None
    assert not report.valid
    assert report.issues[0].code == "migration.spatial_conflict"


def test_spatial_prompt_exposes_reasoning_protocol() -> None:
    prompt = build_modeling_system_prompt("D:/out.stp", _shaft())

    assert "ModelingContract > 用户执行意图" in prompt
    assert "Inventor 数值观测 > 工具成功消息" in prompt
    assert "origin/normal/u/v" in prompt
    assert "禁止根据 XY/XZ/YZ" in prompt
    assert "target_ambiguity" in prompt
    assert "自主选择并调用" in prompt
    assert "系统不会规定固定工具序列" in prompt


def test_conflict_detector_requires_numeric_plane_frame() -> None:
    conflicts = inspect_spatial_result(
        "work_plane",
        {"reference1": "XY"},
        {"status": "success", "data": {"plane": {"name": "Plane1", "normal": [0, 0, 1]}}},
        _shaft(),
    )

    assert conflicts
    assert conflicts[0].conflict_type.value == "plane_orientation"
    assert "origin/normal/u/v" in conflicts[0].detail


@pytest.mark.parametrize(
    ("error", "expected_type"),
    [
        ("multiple matches found; target is ambiguous", "target_ambiguity"),
        ("feature floats outside body and does not intersect", "intersection"),
        ("multiple body count detected", "topology"),
    ],
)
def test_conflict_detector_classifies_tool_failures(error: str, expected_type: str) -> None:
    conflicts = inspect_spatial_result(
        "extrude",
        {"target": "seat", "name": "feature"},
        {"status": "error", "error": error},
        _shaft(),
    )

    assert expected_type in {conflict.conflict_type.value for conflict in conflicts}


def test_conflict_detector_rejects_axial_keyway_direction() -> None:
    conflicts = inspect_spatial_result(
        "cut_keyway",
        {"name": "keyway", "radial_direction": "+X"},
        {"status": "success", "data": {}},
        _shaft(),
    )

    assert "direction" in {conflict.conflict_type.value for conflict in conflicts}



def test_verifier_passes_and_reports_topology_conflict() -> None:
    expectation = compile_contract(_shaft())

    class Evidence:
        def __init__(self, body_count: int) -> None:
            self.body_count = body_count

        async def __call__(self, name: str, args: dict) -> ToolResult:
            if name == "get_body_count":
                return ToolResult(True, {"body_count": self.body_count})
            if name == "get_bounding_box":
                return ToolResult(True, {"size": {"x": 5, "y": 3, "z": 3}})
            if name == "measure_section":
                diameter = 2 if args["position_cm"] < 2 else 3
                return ToolResult(True, {"diameter_cm": diameter})
            return ToolResult(True, {
                "name": "keyway",
                "type": "ExtrudeFeature",
                "min": {"x": 2, "y": -0.25, "z": 1.3},
                "max": {"x": 5, "y": 0.25, "z": 1.5},
            })

    passed = asyncio.run(verify_geometry(expectation, Evidence(1)))
    failed = asyncio.run(verify_geometry(expectation, Evidence(2)))

    assert passed.status.value == "pass"
    assert failed.status.value == "fail"
    assert any(conflict.conflict_type.value == "topology" for conflict in failed.conflicts)


@pytest.mark.asyncio
async def test_modeling_agent_uses_lm_and_repairs_before_export(monkeypatch) -> None:
    agent = object.__new__(ModelingAgent)

    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.messages: list[list[dict]] = []

        async def chat_stream_collect(self, *, messages, tools, **kwargs):
            del kwargs
            self.calls += 1
            self.messages.append(list(messages))
            if self.calls == 1:
                return ModelResponse(tool_calls=[ToolCall("1", "sketch_create", '{"plane":"XY"}')])
            return ModelResponse(tool_calls=[ToolCall("2", "export_step", '{"path":"D:/out.stp"}')])

    class Manager:
        def __init__(self) -> None:
            self.called: list[str] = []

        def is_connected(self, name):
            del name
            return True

        def tools(self, name):
            del name
            return [
                {"name": "sketch_create", "description": "", "input_schema": {}},
                {"name": "export_step", "description": "", "input_schema": {}},
            ]

        async def call(self, server, name, args):
            del server, args
            self.called.append(name)
            if name == "export_step":
                return ToolResult(True, {"path": "D:/out.stp"})
            if name == "get_feature_tree":
                return ToolResult(True, {"features": []})
            return ToolResult(True, {})

    class Report:
        status = type("Status", (), {"value": "pass"})()

        def model_dump(self, **kwargs):
            del kwargs
            return {"status": "pass", "contract_hash": "x", "checks": []}

    client = Client()
    manager = Manager()
    agent.client = client
    agent.manager = manager
    reports = iter([
        GeometryVerificationReport(status=VerificationStatus.FAIL, contract_hash="x"),
        GeometryVerificationReport(status=VerificationStatus.PASS, contract_hash="x"),
    ])
    monkeypatch.setattr(
        agent,
        "_verify",
        lambda expectation: asyncio.sleep(0, result=next(reports)),
    )

    result = await agent.build("自主建模", contract=_shaft(), plan=compile_contract(_shaft()))

    assert result.success
    assert client.calls == 3
    assert "sketch_create" in manager.called
    assert manager.called.index("sketch_create") < manager.called.index("export_step")
    assert any("verification_report" in str(message) for message in client.messages[2])
    assert any(
        "ModelingContract > 用户执行意图" in message.get("content", "")
        for message in client.messages[0]
    )


@pytest.mark.asyncio
async def test_modeling_agent_blocks_export_after_three_failed_repairs(monkeypatch) -> None:
    agent = object.__new__(ModelingAgent)

    class Client:
        async def chat_stream_collect(self, **kwargs):
            del kwargs
            return ModelResponse(tool_calls=[ToolCall("export", "export_step", "{}")])

    class Manager:
        def is_connected(self, name):
            del name
            return True

        def tools(self, name):
            del name
            return [{"name": "export_step", "description": "", "input_schema": {}}]

        async def call(self, server, name, args):
            del server, name, args
            raise AssertionError("验证失败时不得调用真实导出")

    agent.client = Client()
    agent.manager = Manager()
    failed = GeometryVerificationReport(status=VerificationStatus.FAIL, contract_hash="x")
    monkeypatch.setattr(agent, "_verify", lambda expectation: asyncio.sleep(0, result=failed))

    result = await agent.build("建模", contract=_shaft(), plan=compile_contract(_shaft()))

    assert not result.success
    assert result.error == "几何验证连续失败，禁止导出"
    assert result.tool_calls == ["export_step", "export_step", "export_step"]



@pytest.mark.asyncio
async def test_modeling_agent_blocks_export_after_three_failed_repairs(monkeypatch) -> None:
    agent = object.__new__(ModelingAgent)

    class Client:
        async def chat_stream_collect(self, **kwargs):
            del kwargs
            return ModelResponse(tool_calls=[ToolCall("export", "export_step", "{}")])

    class Manager:
        def is_connected(self, name):
            del name
            return True

        def tools(self, name):
            del name
            return [{"name": "export_step", "description": "", "input_schema": {}}]

        async def call(self, server, name, args):
            del server, name, args
            raise AssertionError("验证失败时不得调用真实导出")

    agent.client = Client()
    agent.manager = Manager()
    failed = GeometryVerificationReport(status=VerificationStatus.FAIL, contract_hash="x")
    monkeypatch.setattr(agent, "_verify", lambda expectation: asyncio.sleep(0, result=failed))

    result = await agent.build("建模", contract=_shaft(), plan=compile_contract(_shaft()))

    assert not result.success
    assert result.error == "几何验证连续失败，禁止导出"
    assert result.tool_calls == ["export_step", "export_step", "export_step"]



