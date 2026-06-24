"""Agent 核心循环的流式事件类型。

这些事件将 Agent 核心与渲染层解耦。CLI 渲染器订阅这些事件；
假设的 WebSocket 渲染器可以以不同方式订阅，而无需修改核心循环。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..tools.base import ToolResult


@dataclass
class AgentEvent:
    """事件基类。"""

    pass


@dataclass
class TextDelta(AgentEvent):
    """LLM 返回的文本内容片段。"""

    text: str


@dataclass
class ThinkingStart(AgentEvent):
    """模型开始思考（DeepSeek 推理模式）。"""

    pass


@dataclass
class ThinkingDelta(AgentEvent):
    """思考内容片段。"""

    text: str


@dataclass
class ThinkingEnd(AgentEvent):
    """模型结束思考。"""

    pass


@dataclass
class ToolCallStart(AgentEvent):
    """LLM 即将调用一个工具。"""

    tool_use_id: str
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallEnd(AgentEvent):
    """工具调用完成（包含结果或错误）。"""

    tool_use_id: str
    tool_name: str
    result: ToolResult


@dataclass
class TurnStart(AgentEvent):
    """新的用户轮次已开始。"""

    user_message: str


@dataclass
class TurnComplete(AgentEvent):
    """当前轮次完成（LLM 结束且无更多工具调用）。"""

    stop_reason: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class ErrorEvent(AgentEvent):
    """轮次中发生错误。"""

    message: str
    recoverable: bool = True
