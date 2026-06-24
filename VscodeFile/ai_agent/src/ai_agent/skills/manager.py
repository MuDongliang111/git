"""SkillManager — 技能的生命周期管理。"""

from __future__ import annotations

import logging
from pathlib import Path

from ..tools.registry import ToolRegistry
from .definition import SkillDefinition
from .loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillActivationError(Exception):
    """当技能无法激活时抛出（缺少依赖项）。"""


class SkillManager:
    """管理技能的生命周期：加载、激活、停用。

    Parameters
    ----------
    tool_registry : ToolRegistry
        中央工具注册中心，技能工具在激活时注册，
        停用时移除。
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        self._loader = SkillLoader()
        self._skills: dict[str, SkillDefinition] = {}  # 已加载的技能
        self._active: set[str] = set()  # 已激活的技能名称

    # ------------------------------------------------------------------
    # 加载 / 卸载
    # ------------------------------------------------------------------

    def load_skill(self, skill_path: str | Path) -> SkillDefinition:
        """从磁盘目录加载技能。

        Parameters
        ----------
        skill_path : str | Path
            技能目录的路径。

        Returns
        -------
        SkillDefinition
            加载后的技能定义。

        Raises
        ------
        SkillLoadError
            如果技能目录缺少必需文件。
        ValueError
            如果同名技能已加载。
        """
        skill = self._loader.load(skill_path)
        if skill.name in self._skills:
            raise ValueError(f"技能 '{skill.name}' 已经加载")
        self._skills[skill.name] = skill
        logger.info("已加载技能 '%s' v%s", skill.name, skill.version)
        return skill

    def unload_skill(self, name: str) -> None:
        """卸载技能。如果技能处于激活状态则先停用。"""
        if name in self._active:
            self.deactivate(name)
        self._skills.pop(name, None)
        logger.info("已卸载技能 '%s'", name)

    # ------------------------------------------------------------------
    # 激活 / 停用
    # ------------------------------------------------------------------

    def activate(self, name: str) -> None:
        """激活一个已加载的技能。

        将技能的自定义工具注册到工具注册中心，并将其提示词
        添加到活跃提示词组合中。

        Raises
        ------
        SkillActivationError
            如果技能所需的工具或 MCP 服务器不可用。
        """
        skill = self._skills.get(name)
        if skill is None:
            raise SkillActivationError(f"技能 '{name}' 未加载")

        # 验证依赖项
        available_tools = {
            t.name for t in self._tool_registry.list_all()
        }
        missing_tools = set(skill.requires_tools) - available_tools
        if missing_tools:
            raise SkillActivationError(
                f"技能 '{name}' 需要的工具缺失: {missing_tools}"
            )

        # 注册技能工具
        if skill.tools:
            for tool in skill.tools:
                tool.source = "skill"
                tool.source_name = name
            self._tool_registry.register_batch(skill.tools, source_name=name)

        self._active.add(name)
        logger.info("已激活技能 '%s'（%d 个工具）", name, len(skill.tools))

    def deactivate(self, name: str) -> None:
        """停用技能。从注册中心移除其工具。"""
        if name not in self._active:
            return
        count = self._tool_registry.unregister_by_source(name)
        self._active.discard(name)
        logger.info("已停用技能 '%s'（移除了 %d 个工具）", name, count)

    def deactivate_all(self) -> None:
        """停用所有活跃技能。"""
        for name in list(self._active):
            self.deactivate(name)

    # ------------------------------------------------------------------
    # 提示词组合
    # ------------------------------------------------------------------

    def get_active_prompt(self) -> str:
        """返回所有活跃技能的拼接提示词。"""
        prompts = []
        for name in sorted(self._active):
            skill = self._skills.get(name)
            if skill and skill.prompt:
                prompts.append(f"## 技能: {skill.name}\n{skill.prompt}")
        return "\n\n---\n\n".join(prompts) if prompts else ""

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, name: str) -> SkillDefinition | None:
        """按名称返回已加载的技能，或 ``None``。"""
        return self._skills.get(name)

    def list_available(self) -> list[str]:
        """返回所有已加载技能的名称。"""
        return list(self._skills.keys())

    def list_active(self) -> list[str]:
        """返回当前活跃技能的名称。"""
        return list(sorted(self._active))

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)
