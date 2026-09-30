"""主设计模型的工具集。

导入本包即完成所有工具的注册（各模块顶层的 @register 装饰器执行）。
新增工具只需在对应层的模块里加一个 @register 函数，无需改动 agent_loop。
"""

from . import (  # noqa: F401 - 导入即注册
    compute_tools,
    design_tools,
    express_tools,
    knowledge_tools,
    report_tools,
)
from .registry import (
    ToolContext,
    ToolInterrupt,
    ToolLayer,
    ToolRefusal,
    ToolSpec,
    all_tools,
    build_openai_tools,
    dispatch,
    get_tool,
)

__all__ = [
    "ToolContext",
    "ToolInterrupt",
    "ToolLayer",
    "ToolRefusal",
    "ToolSpec",
    "all_tools",
    "build_openai_tools",
    "dispatch",
    "get_tool",
]
