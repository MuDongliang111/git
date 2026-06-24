"""技能定义数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..tools.base import ToolDefinition


@dataclass
class SkillDefinition:
    """技能包定义。

    技能是一种高级能力，将系统提示词片段与可选的自定义工具
    结合在一起。技能可以声明对内置工具或 MCP 服务器的依赖。
    """

    name: str
    version: str
    description: str
    prompt: str  # 注入到系统提示词中的 Markdown 提示词片段
    tools: list[ToolDefinition] = field(default_factory=list)
    requires_tools: list[str] = field(default_factory=list)
    requires_mcp: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source_path: str = ""  # 技能加载的路径
