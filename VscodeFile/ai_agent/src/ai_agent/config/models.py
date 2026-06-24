"""AI Agent 系统的配置模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent 核心配置。"""

    model: str = Field(
        default="deepseek-v4-pro",
        description="要使用的 DeepSeek 模型 ID",
    )
    max_tokens: int = Field(
        default=4096,
        description="每次 API 响应的最大 token 数",
    )
    max_tool_rounds: int = Field(
        default=10,
        description="每个用户轮次的最大工具调用轮数",
    )
    system_prompt: str = Field(
        default=(
            "你是一个可以使用工具的 AI 助手。"
            "在需要时使用工具来完成用户的请求。"
            "如果无法使用可用工具完成任务，"
            "请说明还需要什么额外的能力。"
        ),
        description="Agent 的基础系统提示词",
    )
    temperature: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="采样温度",
    )
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="high",
        description="DeepSeek 推理深度",
    )
    thinking: bool = Field(
        default=True,
        description="是否启用 DeepSeek 思考模式",
    )


class ToolSettings(BaseModel):
    """单个工具或全局工具的设置。"""

    enabled: list[str] = Field(
        default_factory=lambda: [
            "calculator",
            "web_search",
            "web_fetch",
            "file_read",
            "file_write",
            "file_list",
            "datetime_now",
        ],
        description="启用的内置工具名称列表",
    )
    confirm: list[str] = Field(
        default_factory=lambda: ["file_write"],
        description="执行前需要用户确认的工具列表",
    )


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器连接的配置。"""

    name: str = Field(description="此 MCP 服务器的唯一名称")
    transport: Literal["stdio", "sse"] = Field(
        default="stdio",
        description="传输协议",
    )
    command: str = Field(description="启动 MCP 服务器的命令")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: dict[str, str] = Field(
        default_factory=dict,
        description="额外的环境变量",
    )
    auto_connect: bool = Field(
        default=True,
        description="是否在启动时自动连接",
    )


class AppConfig(BaseModel):
    """顶层应用配置。"""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolSettings = Field(default_factory=ToolSettings)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    skills: list[str] = Field(
        default_factory=list,
        description="启动时自动加载的技能名称",
    )
    skills_dir: str = Field(
        default="./skills",
        description="包含技能包的目录",
    )
    tool_timeout: float = Field(
        default=30.0,
        description="工具执行的默认超时时间（秒）",
    )
