"""Agent 系统中使用的核心工具定义。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolSource = Literal["builtin", "skill", "mcp"]


@dataclass
class ToolDefinition:
    """统一的工具表示。

    每个工具——无论来源（内置、技能、MCP）——都使用此结构表示。
    ``handler`` 可调用对象封装了执行策略，因此注册中心可以
    在不检查工具来源的情况下进行调度。
    """

    name: str
    description: str
    parameters: dict  # 工具输入的 JSON Schema
    handler: Callable[..., Any]  # 异步可调用对象，来源相关的调度
    source: ToolSource = "builtin"
    source_name: str = ""  # 技能名称或 MCP 服务器名称
    requires_confirmation: bool = False

    def to_openai_format(self) -> dict:
        """返回适合 OpenAI ``tools`` 参数的字典格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """单次工具执行的结果。"""

    tool_use_id: str
    name: str
    output: Any  # 字符串或可序列化的字典
    is_error: bool = False
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tool_use_id": self.tool_use_id,
            "name": self.name,
            "output": self.output,
            "is_error": self.is_error,
            "elapsed_ms": self.elapsed_ms,
        }
