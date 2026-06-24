"""将 MCP 工具模式转换为 Agent 的 ToolDefinition 格式。"""

from __future__ import annotations

from typing import Any, Callable

from ..tools.base import ToolDefinition


def translate_mcp_tool(
    server_name: str,
    mcp_tool: Any,
    handler: Callable[..., Any],
) -> ToolDefinition:
    """从 MCP 工具描述符创建 ``ToolDefinition``。

    MCP 服务器通过 ``tools/list`` 返回工具，包含 ``name``、
    ``description`` 和 ``inputSchema`` 字段。我们将其封装为
    Agent 的统一 ``ToolDefinition``，并在名称前加上
    ``mcp.<server_name>.`` 前缀以避免冲突。

    Parameters
    ----------
    server_name : str
        MCP 服务器名称（用于命名空间和生命周期管理）。
    mcp_tool : Any
        来自 MCP ``tools/list`` 响应的工具对象。
        应有 ``name``、``description`` 和 ``inputSchema`` 属性。
    handler : Callable
        一个异步可调用对象，封装了 ``MCPClientManager.call_tool()``。

    Returns
    -------
    ToolDefinition
    """
    tool_name = getattr(mcp_tool, "name", "unknown")
    description = getattr(mcp_tool, "description", "") or ""
    input_schema = getattr(mcp_tool, "inputSchema", {}) or {}

    return ToolDefinition(
        name=f"mcp.{server_name}.{tool_name}",
        description=f"[MCP:{server_name}] {description}",
        parameters=input_schema,
        handler=handler,
        source="mcp",
        source_name=server_name,
    )
