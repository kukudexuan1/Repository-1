"""Unit tests for MCP result normalization and schema bridge."""

from __future__ import annotations

import json

from app.mcp.result import _parse_text
from app.mcp.schema_bridge import mcp_tool_to_function, mcp_tools_to_functions


def test_ansys_success_json_string():
    r = _parse_text(json.dumps({"ok": True, "project_file": "x.wbpj"}))
    assert r.success is True
    assert r.data["project_file"] == "x.wbpj"


def test_ansys_freetext_error():
    r = _parse_text("Error: bridge not running")
    assert r.success is False
    assert "bridge" in r.error


def test_mcpcad_error_contract():
    r = _parse_text(json.dumps({"error": "COM not connected"}))
    assert r.success is False
    assert r.error == "COM not connected"


def test_mcpcad_success_dict():
    r = _parse_text(json.dumps({"success": True, "feature": "Extrusion1"}))
    assert r.success is True
    assert r.data["feature"] == "Extrusion1"


def test_ansys_ok_false():
    r = _parse_text(json.dumps({"ok": False, "error": "RunWB2 not found"}))
    assert r.success is False
    assert "RunWB2" in r.error


def test_plain_text_passthrough():
    r = _parse_text("just some output")
    assert r.success is True
    assert r.text == "just some output"


def test_schema_bridge_single():
    tool = {
        "name": "extrude",
        "description": "extrude a profile",
        "input_schema": {"type": "object", "properties": {"distance": {"type": "number"}}},
    }
    fn = mcp_tool_to_function(tool)
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "extrude"
    assert "distance" in fn["function"]["parameters"]["properties"]


def test_schema_bridge_fills_missing_type():
    tool = {"name": "noop", "description": "", "input_schema": {"properties": {}}}
    fn = mcp_tool_to_function(tool)
    assert fn["function"]["parameters"]["type"] == "object"


def test_schema_bridge_filtering():
    tools = [
        {"name": "a", "description": "", "input_schema": {}},
        {"name": "b", "description": "", "input_schema": {}},
    ]
    only_a = mcp_tools_to_functions(tools, include={"a"})
    assert [f["function"]["name"] for f in only_a] == ["a"]
    no_b = mcp_tools_to_functions(tools, exclude={"b"})
    assert [f["function"]["name"] for f in no_b] == ["a"]
