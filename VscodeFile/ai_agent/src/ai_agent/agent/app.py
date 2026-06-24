"""AgentApp — 依赖注入容器。

将所有组件连接在一起：配置、LLM 客户端、工具注册中心、
MCP 管理器、技能管理器和 Agent 核心。提供统一的
``startup()`` / ``shutdown()`` 生命周期。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.loader import load_config
from ..config.models import AppConfig
from ..mcp.client_manager import MCPClientManager
from ..skills.manager import SkillManager
from ..skills.repository import SkillRepository
from ..tools.builtin.calculator import build_calculator_tool
from ..tools.builtin.datetime_tool import build_datetime_tool
from ..tools.builtin.file_ops import (
    build_file_list_tool,
    build_file_read_tool,
    build_file_write_tool,
)
from ..tools.builtin.web_fetch import build_web_fetch_tool
from ..tools.builtin.web_search import build_web_search_tool
from ..tools.registry import ToolRegistry
from .core import AgentCore
from .llm import LLMClient

logger = logging.getLogger(__name__)

# 内置工具名称到工厂函数的映射
_BUILTIN_FACTORIES: dict[str, callable] = {
    "calculator": build_calculator_tool,
    "web_search": build_web_search_tool,
    "web_fetch": build_web_fetch_tool,
    "file_read": build_file_read_tool,
    "file_write": build_file_write_tool,
    "file_list": build_file_list_tool,
    "datetime_now": build_datetime_tool,
}


class AgentApp:
    """顶层应用，将所有组件连接在一起。

    用法::

        app = AgentApp(["config/default.yaml"])
        await app.startup()
        async for event in app.agent.run("你好！"):
            print(event)
        await app.shutdown()
    """

    def __init__(self, *config_paths: str | Path) -> None:
        self.config: AppConfig = load_config(*config_paths)
        self.llm = LLMClient()
        self.tool_registry = ToolRegistry(
            tool_timeout=self.config.tool_timeout
        )
        self.mcp_manager = MCPClientManager(self.tool_registry)
        self.skill_manager = SkillManager(self.tool_registry)
        self._skill_repo = SkillRepository()

    @property
    def agent(self) -> AgentCore:
        """返回 Agent 核心（在 startup 后延迟初始化）。"""
        return self._agent

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """初始化所有组件。

        1. 注册内置工具
        2. 连接到自动连接的 MCP 服务器
        3. 发现并自动加载技能
        4. 连接 Agent 核心
        """
        # 1. 注册内置工具
        self._register_builtin_tools()

        # 2. 连接 MCP 服务器（auto_connect 的服务器）
        for mcp_config in self.config.mcp_servers:
            if mcp_config.auto_connect:
                try:
                    await self.mcp_manager.connect(mcp_config)
                    logger.info("已连接到 MCP 服务器: %s", mcp_config.name)
                except Exception as exc:
                    logger.error(
                        "无法连接到 MCP 服务器 '%s': %s",
                        mcp_config.name,
                        exc,
                    )

        # 3. 发现并加载技能
        skills_dir = self.config.skills_dir
        skill_paths = self._skill_repo.discover(skills_dir)
        for skill_path in skill_paths:
            try:
                skill = self.skill_manager.load_skill(skill_path)
                logger.info("已加载技能: %s v%s", skill.name, skill.version)
            except Exception as exc:
                logger.error("无法从 %s 加载技能: %s", skill_path, exc)

        # 自动激活配置中指定的技能
        for skill_name in self.config.skills:
            if skill_name in self.skill_manager:
                try:
                    self.skill_manager.activate(skill_name)
                    logger.info("已激活技能: %s", skill_name)
                except Exception as exc:
                    logger.error(
                        "无法激活技能 '%s': %s", skill_name, exc
                    )

        # 4. 连接 Agent 核心
        self._agent = AgentCore(
            config=self.config.agent,
            llm=self.llm,
            tool_registry=self.tool_registry,
            skill_manager=self.skill_manager,
        )

        total_tools = self.tool_registry.count()
        active_skills = len(self.skill_manager.list_active())
        mcp_servers = len(self.mcp_manager.list_servers())

        logger.info(
            "Agent 已启动: %d 个工具, %d 个活跃技能, %d 个 MCP 服务器",
            total_tools,
            active_skills,
            mcp_servers,
        )

    async def shutdown(self) -> None:
        """清理所有资源。"""
        self.skill_manager.deactivate_all()
        await self.mcp_manager.disconnect_all()
        logger.info("Agent 已关闭")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _register_builtin_tools(self) -> None:
        """根据配置注册已启用的内置工具。"""
        enabled = set(self.config.tools.enabled)
        confirm_set = set(self.config.tools.confirm)

        for name, factory in _BUILTIN_FACTORIES.items():
            if name in enabled:
                tool = factory()
                if name in confirm_set:
                    tool.requires_confirmation = True
                self.tool_registry.register(tool)

        logger.info("已注册 %d 个内置工具", len(enabled))
