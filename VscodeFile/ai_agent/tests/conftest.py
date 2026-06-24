"""ai_agent 测试的共享 fixtures。"""

import os
from pathlib import Path

import pytest


@pytest.fixture
def test_config_path(tmp_path: Path) -> str:
    """创建用于测试的最小临时配置文件。"""
    config_content = """
agent:
  model: "deepseek-v4-pro"
  max_tokens: 1024
  max_tool_rounds: 3
  reasoning_effort: "high"
  thinking: true

tools:
  enabled:
    - calculator
  confirm: []

skills_dir: "./skills"
tool_timeout: 5.0
mcp_servers: []
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def mock_api_key(monkeypatch) -> None:
    """设置用于测试的假 API Key。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test-key-12345")


@pytest.fixture
def test_skills_dir(tmp_path: Path) -> str:
    """创建包含测试技能的临时技能目录。"""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()

    (skill_dir / "skill.yaml").write_text("""
name: test_skill
version: "1.0.0"
description: "一个测试技能"
requires_tools: []
""")

    (skill_dir / "prompt.md").write_text("## 测试技能\n这是一个测试提示词。")

    (skill_dir / "tools.py").write_text("""
def get_tools():
    return []
""")

    return str(tmp_path)
