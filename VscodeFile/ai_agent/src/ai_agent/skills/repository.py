"""技能仓库 — 在磁盘上发现技能目录。"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillRepository:
    """扫描目录以查找有效的技能包。

    一个有效的技能目录必须至少包含一个 ``skill.yaml`` 文件
    和一个 ``prompt.md`` 文件。
    """

    def discover(self, skills_dir: str | Path) -> list[str]:
        """在 *skills_dir* 下发现技能目录。

        Parameters
        ----------
        skills_dir : str | Path
            包含技能子目录的根目录。

        Returns
        -------
        list[str]
            发现的技能目录的绝对路径列表。
        """
        root = Path(skills_dir)
        if not root.exists():
            # 相对路径 — 尝试从当前工作目录和包目录解析
            root = Path.cwd() / skills_dir
        if not root.exists():
            logger.debug("未找到技能目录: %s", skills_dir)
            return []

        discovered: list[str] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            # 跳过隐藏目录和 __pycache__
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            # 检查必需文件
            if (entry / "skill.yaml").exists() and (entry / "prompt.md").exists():
                discovered.append(str(entry.resolve()))
            else:
                logger.debug("跳过非技能目录: %s", entry.name)

        logger.info("在 %s 中发现了 %d 个技能", len(discovered), root)
        return discovered
