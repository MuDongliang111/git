"""工具注册中心 — 所有工具来源的中央调度器。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .base import ToolDefinition, ToolResult, ToolSource

logger = logging.getLogger(__name__)


class ToolRegistry:
    """所有工具的中央注册中心。

    工具可以来自三种来源：

    * ``builtin``  — 启动时自动注册
    * ``skill``    — 技能激活时注册
    * ``mcp``      — MCP 服务器连接时注册

    注册中心强制名称唯一性，并支持技能激活/停用
    和 MCP 连接/断开的批量操作。
    """

    def __init__(self, tool_timeout: float = 30.0) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._tool_timeout = tool_timeout

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """注册单个工具。名称冲突时抛出 ValueError。"""
        if tool.name in self._tools:
            raise ValueError(f"工具 '{tool.name}' 已经注册")
        self._tools[tool.name] = tool
        logger.debug("已注册工具: %s (source=%s)", tool.name, tool.source)

    def register_batch(
        self, tools: list[ToolDefinition], source_name: str = ""
    ) -> None:
        """批量注册工具，通常来自一个技能或 MCP 服务器。"""
        for tool in tools:
            if source_name:
                tool.source_name = source_name
            self.register(tool)

    def unregister(self, name: str) -> None:
        """按名称移除单个工具。如果未找到则无操作。"""
        if name in self._tools:
            del self._tools[name]
            logger.debug("已注销工具: %s", name)

    def unregister_by_source(self, source_name: str) -> int:
        """移除来自指定来源（技能名称或 MCP 服务器）的所有工具。

        返回移除的工具数量。
        """
        names = [
            name
            for name, tool in self._tools.items()
            if tool.source_name == source_name
        ]
        for name in names:
            del self._tools[name]
        if names:
            logger.debug(
                "从来源 '%s' 注销了 %d 个工具", source_name, len(names)
            )
        return len(names)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, name: str) -> ToolDefinition | None:
        """按名称返回工具定义，或 ``None``。"""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDefinition]:
        """返回所有已注册的工具。"""
        return list(self._tools.values())

    def names_by_source(self, source: ToolSource) -> list[str]:
        """返回特定来源类型的工具名称。"""
        return [n for n, t in self._tools.items() if t.source == source]

    def count(self) -> int:
        """返回已注册的工具数量。"""
        return len(self._tools)

    def search(self, query: str) -> list[ToolDefinition]:
        """对工具名称和描述进行不区分大小写的子串搜索。"""
        q = query.lower()
        return [
            t
            for t in self._tools.values()
            if q in t.name.lower() or q in t.description.lower()
        ]

    # ------------------------------------------------------------------
    # OpenAI 格式
    # ------------------------------------------------------------------

    def to_openai_format(self) -> list[dict]:
        """将所有已注册工具转换为 OpenAI API ``tools`` 格式。"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def execute(
        self, tool_use_id: str, name: str, params: dict[str, Any]
    ) -> ToolResult:
        """按名称执行工具并返回结果。

        处理器使用 ``**params`` 方式调用。错误会被捕获并以
        ``ToolResult(is_error=True)`` 返回，以便 LLM 自行纠正。
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_use_id=tool_use_id,
                name=name,
                output=f"错误: 工具 '{name}' 未注册",
                is_error=True,
            )

        start = time.time()
        try:
            # 带超时执行
            coro = tool.handler(**params)
            if asyncio.iscoroutine(coro):
                output = await asyncio.wait_for(coro, timeout=self._tool_timeout)
            else:
                output = coro
            elapsed = (time.time() - start) * 1000
            return ToolResult(
                tool_use_id=tool_use_id,
                name=name,
                output=str(output) if not isinstance(output, (dict, list)) else output,
                elapsed_ms=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            return ToolResult(
                tool_use_id=tool_use_id,
                name=name,
                output=f"错误: 工具 '{name}' 在 {self._tool_timeout}s 后超时",
                is_error=True,
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            logger.exception("工具 '%s' 执行失败", name)
            return ToolResult(
                tool_use_id=tool_use_id,
                name=name,
                output=f"执行 '{name}' 时出错: {exc}",
                is_error=True,
                elapsed_ms=elapsed,
            )
