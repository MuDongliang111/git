"""MCP 客户端管理器 — 管理 MCP 服务器连接和工具发现。"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from ..config.models import MCPServerConfig
from ..tools.base import ToolDefinition
from .tool_translator import translate_mcp_tool

logger = logging.getLogger(__name__)


class MCPClientManager:
    """管理与 MCP 服务器的连接。

    处理以下功能：
    - 启动 MCP 服务器子进程（stdio 传输）
    - 初始化 MCP 会话
    - 通过 ``tools/list`` 发现工具
    - 通过 ``tools/call`` 调用工具
    - 优雅断开和清理

    Parameters
    ----------
    tool_registry : ToolRegistry
        中央工具注册中心，发现的 MCP 工具在连接时注册，
        断开时移除。
    """

    def __init__(self, tool_registry) -> None:
        self._tool_registry = tool_registry
        self._sessions: dict[str, Any] = {}  # server_name -> ClientSession
        self._transports: dict[str, tuple[Any, Any]] = {}  # server_name -> (read, write)
        self._server_configs: dict[str, MCPServerConfig] = {}

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------

    async def connect(self, config: MCPServerConfig) -> None:
        """连接到 MCP 服务器。

        1. 启动服务器子进程（stdio 传输）
        2. 初始化 MCP 会话
        3. 发现工具并注册

        Parameters
        ----------
        config : MCPServerConfig
            服务器连接配置。

        Raises
        ------
        ValueError
            如果同名服务器已经连接。
        RuntimeError
            如果连接或初始化失败。
        """
        if config.name in self._sessions:
            raise ValueError(f"MCP 服务器 '{config.name}' 已经连接")

        logger.info("正在连接到 MCP 服务器 '%s'...", config.name)

        try:
            if config.transport == "stdio":
                await self._connect_stdio(config)
            else:
                raise ValueError(f"不支持的传输协议: {config.transport}")

            self._server_configs[config.name] = config

            # 发现并注册工具
            count = await self.discover_and_register(config.name)
            logger.info(
                "MCP 服务器 '%s' 已连接，共 %d 个工具", config.name, count
            )
        except Exception:
            # 失败时清理部分连接
            await self._cleanup_server(config.name)
            raise

    async def disconnect(self, server_name: str) -> None:
        """断开与 MCP 服务器的连接。

        注销所有相关工具并终止子进程。

        Parameters
        ----------
        server_name : str
            要断开的服务器名称。
        """
        if server_name not in self._sessions:
            return

        # 先注销工具
        removed = self._tool_registry.unregister_by_source(server_name)
        logger.info(
            "从 MCP 服务器 '%s' 注销了 %d 个工具", server_name, removed
        )

        await self._cleanup_server(server_name)
        self._server_configs.pop(server_name, None)
        logger.info("已断开与 MCP 服务器 '%s' 的连接", server_name)

    async def disconnect_all(self) -> None:
        """断开所有 MCP 服务器的连接。"""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)

    # ------------------------------------------------------------------
    # 工具操作
    # ------------------------------------------------------------------

    async def discover_and_register(self, server_name: str) -> int:
        """从已连接的 MCP 服务器发现工具并注册。

        Parameters
        ----------
        server_name : str
            要查询的服务器名称。

        Returns
        -------
        int
            发现并注册的工具数量。
        """
        session = self._sessions.get(server_name)
        if session is None:
            raise ValueError(f"MCP 服务器 '{server_name}' 未连接")

        try:
            result = await session.list_tools()
        except Exception as exc:
            logger.error(
                "无法从 '%s' 列出工具: %s", server_name, exc
            )
            return 0

        tools: list[ToolDefinition] = []
        for mcp_tool in result.tools:
            handler = self._make_mcp_handler(server_name, mcp_tool.name)
            td = translate_mcp_tool(server_name, mcp_tool, handler)
            tools.append(td)

        if tools:
            self._tool_registry.register_batch(tools, source_name=server_name)

        return len(tools)

    async def call_tool(
        self, server_name: str, tool_name: str, args: dict[str, Any]
    ) -> Any:
        """在已连接的 MCP 服务器上调用工具。

        Parameters
        ----------
        server_name : str
            MCP 服务器名称。
        tool_name : str
            工具名称（不含 ``mcp.<server>.`` 前缀）。
        args : dict
            工具参数。

        Returns
        -------
        Any
            工具返回的内容。

        Raises
        ------
        ValueError
            如果服务器未连接。
        RuntimeError
            如果工具调用失败。
        """
        session = self._sessions.get(server_name)
        if session is None:
            raise ValueError(f"MCP 服务器 '{server_name}' 未连接")

        try:
            result = await session.call_tool(tool_name, args)
            # 从结果中提取文本内容
            if result.content:
                parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                return "\n".join(parts) if parts else "(空结果)"
            return str(result)
        except Exception as exc:
            logger.error(
                "MCP 工具调用失败: %s/%s -> %s", server_name, tool_name, exc
            )
            raise RuntimeError(
                f"MCP 工具 '{server_name}/{tool_name}' 失败: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_servers(self) -> list[str]:
        """返回当前已连接的 MCP 服务器名称列表。"""
        return list(self._sessions.keys())

    def is_connected(self, server_name: str) -> bool:
        """检查某个服务器是否已连接。"""
        return server_name in self._sessions

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _connect_stdio(self, config: MCPServerConfig) -> None:
        """建立基于 stdio 的 MCP 连接。"""
        try:
            from mcp.client.stdio import stdio_client
            from mcp import ClientSession
        except ImportError as exc:
            raise RuntimeError(
                "未安装 MCP SDK。使用以下命令安装: pip install mcp"
            ) from exc

        # 构建环境变量
        env = os.environ.copy()
        env.update(config.env)

        logger.debug(
            "启动 MCP 服务器: %s %s",
            config.command,
            " ".join(config.args),
        )

        server_params = {
            "command": config.command,
            "args": config.args,
            "env": env,
        }

        # 创建 stdio 客户端上下文
        stdio_ctx = stdio_client(server_params)
        read, write = await stdio_ctx.__aenter__()

        # 创建会话
        session_ctx = ClientSession(read, write)
        session = await session_ctx.__aenter__()

        # 初始化
        await session.initialize()

        self._transports[config.name] = (read, write)
        self._sessions[config.name] = session

        # 存储上下文管理器以便后续清理
        self._stdio_contexts = getattr(self, "_stdio_contexts", {})
        self._stdio_contexts[config.name] = stdio_ctx
        self._session_contexts = getattr(self, "_session_contexts", {})
        self._session_contexts[config.name] = session_ctx

    async def _cleanup_server(self, server_name: str) -> None:
        """清理服务器资源（会话、传输、子进程）。"""
        # 清理会话上下文
        session_ctx = getattr(self, "_session_contexts", {}).pop(server_name, None)
        if session_ctx:
            try:
                await session_ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug("关闭 '%s' 的会话时出错: %s", server_name, exc)

        # 清理 stdio 上下文
        stdio_ctx = getattr(self, "_stdio_contexts", {}).pop(server_name, None)
        if stdio_ctx:
            try:
                await stdio_ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug("关闭 '%s' 的 stdio 时出错: %s", server_name, exc)

        self._sessions.pop(server_name, None)
        self._transports.pop(server_name, None)

    def _make_mcp_handler(self, server_name: str, tool_name: str):
        """为 MCP 工具创建一个处理器闭包。

        闭包捕获 *server_name* 和 *tool_name*，以便工具注册中心
        可以在不了解 MCP 内部细节的情况下进行调度。
        """

        async def _handler(**kwargs: Any) -> str:
            return await self.call_tool(server_name, tool_name, kwargs)

        # 存储元数据以便调试
        _handler.__name__ = f"mcp_{server_name}_{tool_name}"
        return _handler
