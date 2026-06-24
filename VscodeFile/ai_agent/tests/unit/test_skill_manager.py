"""SkillManager 的测试。"""

import pytest

from ai_agent.skills.definition import SkillDefinition
from ai_agent.skills.manager import SkillManager, SkillActivationError
from ai_agent.skills.loader import SkillLoader, SkillLoadError
from ai_agent.skills.repository import SkillRepository
from ai_agent.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry():
    return ToolRegistry()


@pytest.fixture
def skill_manager(tool_registry):
    return SkillManager(tool_registry)


@pytest.fixture
def sample_skill_def():
    return SkillDefinition(
        name="test_skill",
        version="1.0.0",
        description="一个测试技能",
        prompt="## 测试技能\n这是一个测试。",
        tools=[],
        requires_tools=[],
    )


class TestSkillLoader:
    def test_load_valid_skill(self, test_skills_dir):
        loader = SkillLoader()
        skill_path = f"{test_skills_dir}/test_skill"
        skill = loader.load(skill_path)
        assert skill.name == "test_skill"
        assert skill.version == "1.0.0"
        assert "测试技能" in skill.prompt

    def test_load_nonexistent_dir(self):
        loader = SkillLoader()
        with pytest.raises(SkillLoadError, match="不是目录"):
            loader.load("/nonexistent/path")

    def test_load_missing_skill_yaml(self, tmp_path):
        skill_dir = tmp_path / "incomplete"
        skill_dir.mkdir()
        loader = SkillLoader()
        with pytest.raises(SkillLoadError, match="缺少必需文件"):
            loader.load(str(skill_dir))

    def test_load_missing_prompt_md(self, tmp_path):
        skill_dir = tmp_path / "no_prompt"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: test\nversion: '1.0'")
        loader = SkillLoader()
        with pytest.raises(SkillLoadError, match="缺少必需文件"):
            loader.load(str(skill_dir))


class TestSkillRepository:
    def test_discover_skills(self, test_skills_dir):
        repo = SkillRepository()
        paths = repo.discover(test_skills_dir)
        assert len(paths) >= 1
        assert any("test_skill" in p for p in paths)

    def test_discover_empty_dir(self, tmp_path):
        repo = SkillRepository()
        paths = repo.discover(str(tmp_path))
        assert len(paths) == 0

    def test_discover_nonexistent_dir(self):
        repo = SkillRepository()
        paths = repo.discover("/nonexistent/skills")
        assert len(paths) == 0


class TestSkillManager:
    def test_load_skill_from_path(self, skill_manager, test_skills_dir):
        skill_path = f"{test_skills_dir}/test_skill"
        skill = skill_manager.load_skill(skill_path)
        assert skill.name == "test_skill"
        assert "test_skill" in skill_manager

    def test_load_duplicate_raises(self, skill_manager, test_skills_dir):
        skill_path = f"{test_skills_dir}/test_skill"
        skill_manager.load_skill(skill_path)
        with pytest.raises(ValueError, match="已经加载"):
            skill_manager.load_skill(skill_path)

    def test_activate_deactivate(self, skill_manager, sample_skill_def, tool_registry):
        # 手动插入技能以绕过加载步骤
        skill_manager._skills[sample_skill_def.name] = sample_skill_def

        skill_manager.activate("test_skill")
        assert "test_skill" in skill_manager.list_active()

        skill_manager.deactivate("test_skill")
        assert "test_skill" not in skill_manager.list_active()

    def test_activate_unknown_skill(self, skill_manager):
        with pytest.raises(SkillActivationError, match="未加载"):
            skill_manager.activate("nonexistent")

    def test_get_active_prompt(self, skill_manager, sample_skill_def):
        skill_manager._skills[sample_skill_def.name] = sample_skill_def
        skill_manager.activate("test_skill")

        prompt = skill_manager.get_active_prompt()
        assert "测试技能" in prompt

    def test_deactivate_all(self, skill_manager, sample_skill_def):
        skill_manager._skills[sample_skill_def.name] = sample_skill_def
        skill_manager.activate("test_skill")
        skill_manager.deactivate_all()
        assert len(skill_manager.list_active()) == 0

    def test_unload_skill(self, skill_manager, sample_skill_def):
        skill_manager._skills[sample_skill_def.name] = sample_skill_def
        skill_manager.activate("test_skill")
        skill_manager.unload_skill("test_skill")
        assert "test_skill" not in skill_manager

    def test_list_available(self, skill_manager, sample_skill_def):
        skill_manager._skills[sample_skill_def.name] = sample_skill_def
        assert "test_skill" in skill_manager.list_available()
