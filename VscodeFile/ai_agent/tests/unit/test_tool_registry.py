"""ToolRegistry 的测试。"""

import pytest

from ai_agent.tools.base import ToolDefinition, ToolResult
from ai_agent.tools.registry import ToolRegistry


async def _echo_handler(**kwargs):
    return f"echo: {kwargs}"


async def _error_handler(**kwargs):
    raise RuntimeError("故意抛出错误")


async def _slow_handler(**kwargs):
    import asyncio
    await asyncio.sleep(10)
    return "done"


@pytest.fixture
def registry():
    return ToolRegistry(tool_timeout=2.0)


@pytest.fixture
def echo_tool():
    return ToolDefinition(
        name="echo",
        description="回显参数",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"],
        },
        handler=_echo_handler,
        source="builtin",
    )


class TestRegistration:
    def test_register_single(self, registry, echo_tool):
        registry.register(echo_tool)
        assert registry.count() == 1
        assert registry.get("echo") is echo_tool

    def test_register_duplicate_raises(self, registry, echo_tool):
        registry.register(echo_tool)
        with pytest.raises(ValueError, match="已经注册"):
            registry.register(echo_tool)

    def test_register_batch(self, registry):
        tools = [
            ToolDefinition(
                name=f"tool_{i}",
                description=f"工具 {i}",
                parameters={"type": "object", "properties": {}},
                handler=_echo_handler,
                source="skill",
            )
            for i in range(5)
        ]
        registry.register_batch(tools, source_name="test_skill")
        assert registry.count() == 5
        for i in range(5):
            assert registry.get(f"tool_{i}").source_name == "test_skill"

    def test_unregister(self, registry, echo_tool):
        registry.register(echo_tool)
        registry.unregister("echo")
        assert registry.count() == 0

    def test_unregister_nonexistent(self, registry):
        # 不应抛出异常
        registry.unregister("nonexistent")

    def test_unregister_by_source(self, registry):
        tools = [
            ToolDefinition(
                name=f"t_{i}",
                description="...",
                parameters={},
                handler=_echo_handler,
                source="skill",
                source_name="skill_a",
            )
            for i in range(3)
        ] + [
            ToolDefinition(
                name=f"t_{i+3}",
                description="...",
                parameters={},
                handler=_echo_handler,
                source="skill",
                source_name="skill_b",
            )
            for i in range(2)
        ]
        registry.register_batch(tools)

        removed = registry.unregister_by_source("skill_a")
        assert removed == 3
        assert registry.count() == 2
        assert all(t.source_name == "skill_b" for t in registry.list_all())


class TestQuery:
    def test_list_all(self, registry):
        tools = [
            ToolDefinition(
                name="a", description="描述 a", parameters={},
                handler=_echo_handler, source="builtin",
            ),
            ToolDefinition(
                name="b", description="描述 b", parameters={},
                handler=_echo_handler, source="skill", source_name="s1",
            ),
        ]
        registry.register_batch(tools)
        assert len(registry.list_all()) == 2

    def test_search_by_name(self, registry):
        registry.register(ToolDefinition(
            name="calculator", description="数学工具", parameters={},
            handler=_echo_handler, source="builtin",
        ))
        results = registry.search("math")
        assert len(results) == 0  # 搜索中文
        results = registry.search("calc")
        assert len(results) == 1
        assert results[0].name == "calculator"

    def test_search_by_description(self, registry):
        registry.register(ToolDefinition(
            name="web_search", description="搜索互联网", parameters={},
            handler=_echo_handler, source="builtin",
        ))
        results = registry.search("搜索")
        assert len(results) == 1

    def test_search_no_match(self, registry):
        results = registry.search("不存在的工具")
        assert len(results) == 0

    def test_names_by_source(self, registry):
        registry.register(ToolDefinition(
            name="t1", description="...", parameters={},
            handler=_echo_handler, source="builtin",
        ))
        registry.register(ToolDefinition(
            name="t2", description="...", parameters={},
            handler=_echo_handler, source="skill", source_name="sk",
        ))
        builtin_names = registry.names_by_source("builtin")
        assert builtin_names == ["t1"]

    def test_to_openai_format(self, registry, echo_tool):
        registry.register(echo_tool)
        fmt = registry.to_openai_format()
        assert len(fmt) == 1
        assert fmt[0]["type"] == "function"
        assert fmt[0]["function"]["name"] == "echo"
        assert "parameters" in fmt[0]["function"]


class TestExecution:
    @pytest.mark.asyncio
    async def test_execute_success(self, registry, echo_tool):
        registry.register(echo_tool)
        result = await registry.execute("tu_1", "echo", {"message": "hello"})
        assert not result.is_error
        assert "hello" in str(result.output)
        assert result.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry):
        result = await registry.execute("tu_1", "nonexistent", {})
        assert result.is_error
        assert "未注册" in str(result.output)

    @pytest.mark.asyncio
    async def test_execute_handler_error(self, registry):
        tool = ToolDefinition(
            name="error_tool",
            description="总是出错",
            parameters={},
            handler=_error_handler,
            source="builtin",
        )
        registry.register(tool)
        result = await registry.execute("tu_1", "error_tool", {})
        assert result.is_error
        assert "故意抛出错误" in str(result.output)

    @pytest.mark.asyncio
    async def test_execute_timeout(self, registry):
        tool = ToolDefinition(
            name="slow_tool",
            description="非常慢",
            parameters={},
            handler=_slow_handler,
            source="builtin",
        )
        registry.register(tool)
        result = await registry.execute("tu_1", "slow_tool", {})
        assert result.is_error
        assert "超时" in str(result.output)
