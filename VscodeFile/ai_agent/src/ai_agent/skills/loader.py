"""技能加载器 — 将技能目录解析为 SkillDefinition。"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import yaml

from .definition import SkillDefinition

logger = logging.getLogger(__name__)

_REQUIRED_FILES = ("skill.yaml", "prompt.md")


class SkillLoadError(Exception):
    """技能加载失败时抛出。"""


class SkillLoader:
    """从磁盘目录加载技能。

    预期的目录结构::

        skill_name/
        ├── skill.yaml     # 元数据
        ├── prompt.md      # 系统提示词片段
        └── tools.py       # （可选）自定义工具
    """

    def load(self, skill_path: str | Path) -> SkillDefinition:
        """解析技能目录并返回 SkillDefinition。

        Parameters
        ----------
        skill_path : str | Path
            技能目录的路径。

        Returns
        -------
        SkillDefinition

        Raises
        ------
        SkillLoadError
            如果必需文件缺失或格式错误。
        """
        path = Path(skill_path).resolve()
        if not path.is_dir():
            raise SkillLoadError(f"技能路径不是目录: {path}")

        # --- 加载 skill.yaml ---
        yaml_path = path / "skill.yaml"
        if not yaml_path.exists():
            raise SkillLoadError(f"缺少必需文件: {yaml_path}")
        try:
            metadata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SkillLoadError(f"{yaml_path} 中的 YAML 格式无效: {exc}") from exc

        if not isinstance(metadata, dict):
            raise SkillLoadError(f"{yaml_path} 必须包含一个 YAML 映射")

        name = metadata.get("name", path.name)

        # --- 加载 prompt.md ---
        prompt_path = path / "prompt.md"
        if not prompt_path.exists():
            raise SkillLoadError(f"缺少必需文件: {prompt_path}")
        prompt = prompt_path.read_text(encoding="utf-8").strip()

        # --- 加载 tools.py（可选） ---
        tools = []
        tools_path = path / "tools.py"
        if tools_path.exists():
            tools = self._load_tools(tools_path)

        return SkillDefinition(
            name=name,
            version=str(metadata.get("version", "0.0.0")),
            description=metadata.get("description", ""),
            prompt=prompt,
            tools=tools,
            requires_tools=metadata.get("requires_tools", []),
            requires_mcp=metadata.get("requires_mcp", []),
            metadata=metadata,
            source_path=str(path),
        )

    def _load_tools(self, tools_path: Path) -> list:
        """从 ``tools.py`` 文件动态导入工具。

        该模块必须暴露一个 ``get_tools() -> list[ToolDefinition]`` 函数。
        """
        spec = importlib.util.spec_from_file_location(
            f"skill_tools_{tools_path.parent.name}", tools_path
        )
        if spec is None or spec.loader is None:
            logger.warning("无法为 %s 加载模块规格", tools_path)
            return []

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.error("导入 %s 失败: %s", tools_path, exc)
            return []

        get_tools = getattr(module, "get_tools", None)
        if callable(get_tools):
            try:
                return get_tools()
            except Exception as exc:
                logger.error("%s 中的 get_tools() 失败: %s", tools_path, exc)
                return []

        return []
