"""配置加载器的测试。"""

from pathlib import Path

import pytest

from ai_agent.config.loader import load_config, _interpolate_env_vars, _deep_merge
from ai_agent.config.models import AppConfig, AgentConfig


class TestDeepMerge:
    def test_shallow_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"parent": {"x": 1, "y": 2}}
        override = {"parent": {"y": 99, "z": 3}}
        result = _deep_merge(base, override)
        assert result == {"parent": {"x": 1, "y": 99, "z": 3}}

    def test_list_replacement(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = _deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_new_keys(self):
        base = {"a": 1}
        override = {"b": {"nested": True}}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": {"nested": True}}


class TestEnvInterpolation:
    def test_simple_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        result = _interpolate_env_vars("prefix/${TEST_VAR}/suffix")
        assert result == "prefix/hello/suffix"

    def test_missing_var(self):
        result = _interpolate_env_vars("${NONEXISTENT_VAR}")
        assert result == "${NONEXISTENT_VAR}"

    def test_no_var(self):
        result = _interpolate_env_vars("plain text")
        assert result == "plain text"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        result = _interpolate_env_vars("${A} + ${B} = 3")
        assert result == "1 + 2 = 3"


class TestLoadConfig:
    def test_load_defaults(self, test_config_path):
        config = load_config(test_config_path)
        assert isinstance(config, AppConfig)
        assert config.agent.model == "deepseek-v4-pro"
        assert config.agent.max_tokens == 1024
        assert config.agent.max_tool_rounds == 3
        assert config.tool_timeout == 5.0

    def test_merge_configs(self, tmp_path):
        base = tmp_path / "base.yaml"
        base.write_text("agent:\n  model: \"model-1\"\n  max_tokens: 100")

        override = tmp_path / "override.yaml"
        override.write_text("agent:\n  max_tokens: 200")

        config = load_config(str(base), str(override))
        assert config.agent.model == "model-1"
        assert config.agent.max_tokens == 200

    def test_missing_file_skipped(self, tmp_path):
        """缺失的配置文件应被静默跳过。"""
        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert isinstance(config, AppConfig)
        # 应具有默认值
        assert isinstance(config.agent, AgentConfig)
