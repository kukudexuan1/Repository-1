"""
experiment.py — 实验条件与工具白名单映射。

各实验脚本通过请求头 X-Experiment-Condition 传入条件标识，
workflow / stream 路由读取后查此映射，把允许工具集和标志注入 AgentLoop。

None 表示不限制（完整框架 P），frozenset() 表示不提供任何工具（B0 纯LLM）。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 各层工具名分组（与 ToolLayer 对应）
# ---------------------------------------------------------------------------

_KNOWLEDGE: frozenset[str] = frozenset({
    "search_formula",
    "lookup_material",
    "lookup_standard_series",
    "lookup_standard_part",
    "list_design_families",
})

_BASIC_INTERACTION: frozenset[str] = frozenset({
    "start_design",
    "update_design_spec",
})

_COMPUTE: frozenset[str] = frozenset({
    "solve_formula",
    "run_calculation",
})

_LEDGER: frozenset[str] = frozenset({
    "commit_parameter",
    "query_ledger",
    "get_calculation_record",
})

_GATE: frozenset[str] = frozenset({
    "freeze_parameters",
    "unfreeze_parameters",
    "propose_design_alternatives",
    "confirm_scheme",
    "request_user_decision",
    "set_design_scope",
    "set_design_stage",
    "declare_assembly_parts",
})

_EXPRESSION: frozenset[str] = frozenset({
    "analyze_drawing",
    "plan_modeling_contract",
    "build_model",
    "run_simulation",
    "accept_verification",
    "submit_assembly_geometry",
})

_DELIVERY: frozenset[str] = frozenset({
    "generate_design_report",
})

# ---------------------------------------------------------------------------
# 条件 → 工具白名单
# None = 不限制（全部工具），frozenset() = 不提供任何工具
# ---------------------------------------------------------------------------

CONDITION_TOOLS: dict[str, frozenset[str] | None] = {
    # B-EXT 完全绕过 backend，此映射不会被调用
    "B_EXT": None,
    # B0：纯 LLM，无任何工具
    "B0": frozenset(),
    # B1：LLM + 普通RAG（知识检索作为文本上下文，无计算台账Gate）
    "B1": _KNOWLEDGE | _BASIC_INTERACTION,
    # B2：LLM + 计算工具（无证据强制、无Gate、无失效传播）
    "B2": _KNOWLEDGE | _BASIC_INTERACTION | _COMPUTE,
    # B3：LLM + 证据台账（有台账，无Gate，无失效传播）
    "B3": _KNOWLEDGE | _BASIC_INTERACTION | _COMPUTE | _LEDGER,
    # B4：LLM + 台账 + Gate（有台账和Gate，无增量失效传播）
    "B4": _KNOWLEDGE | _BASIC_INTERACTION | _COMPUTE | _LEDGER | _GATE,
    # E5_C1：Prompt-only，与 B0 同样不提供工具，但名称独立以固定实验语义。
    "E5_C1": frozenset(),
    # E5_C2：完整工具集，Gate 是否执行由 flags 控制。
    "E5_C2": None,
    # P：完整框架
    "P": None,
}

# ---------------------------------------------------------------------------
# 条件 → 运行时标志（注入 AgentLoop.experiment_flags / ToolContext.extras）
# ---------------------------------------------------------------------------

CONDITION_FLAGS: dict[str, dict[str, bool]] = {
    "B0": {"propagation_enabled": False, "gate_enabled": False, "evidence_required": False},
    "B1": {"propagation_enabled": False, "gate_enabled": False, "evidence_required": False},
    "B2": {"propagation_enabled": False, "gate_enabled": False, "evidence_required": False},
    "B3": {"propagation_enabled": False, "gate_enabled": False, "evidence_required": True},
    "B4": {"propagation_enabled": False, "gate_enabled": True,  "evidence_required": True},
    "E5_C1": {"propagation_enabled": False, "gate_enabled": False, "evidence_required": False},
    "E5_C2": {"propagation_enabled": True,  "gate_enabled": False, "evidence_required": False},
    "P":  {"propagation_enabled": True,  "gate_enabled": True,  "evidence_required": True},
}

_DEFAULT_FLAGS: dict[str, bool] = {
    "propagation_enabled": True,
    "gate_enabled": True,
    "evidence_required": True,
}


def resolve_condition(condition_header: str | None) -> tuple[frozenset[str] | None, dict[str, bool]]:
    """
    根据请求头值返回 (allowed_tools, flags)。

    allowed_tools=None   → 不限制，全部工具可用（P 或未设置条件时）
    allowed_tools=frozenset() → 无工具（B0）
    """
    if not condition_header:
        return None, dict(_DEFAULT_FLAGS)
    cond = condition_header.strip().upper()
    tools = CONDITION_TOOLS.get(cond)
    flags = dict(CONDITION_FLAGS.get(cond, _DEFAULT_FLAGS))
    return tools, flags
