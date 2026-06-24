"""Agent 完整循环的集成测试（使用 mock LLM）。"""

import pytest

from ai_agent.agent.history import ConversationHistory
from ai_agent.agent.events import (
    TextDelta,
    ToolCallStart,
    ToolCallEnd,
    TurnComplete,
    ErrorEvent,
)
from ai_agent.tools.base import ToolDefinition
from ai_agent.tools.registry import ToolRegistry


class TestConversationHistory:
    def test_append_user_message(self):
        history = ConversationHistory()
        history.append_user_message("你好")
        msgs = history.to_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "你好"

    def test_append_assistant_text(self):
        history = ConversationHistory()
        history.append_assistant_message(text="你好！")
        msgs = history.to_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] == "你好！"

    def test_append_assistant_with_tool_uses(self):
        history = ConversationHistory()
        history.append_assistant_message(
            text="让我算一下。",
            tool_uses=[
                {"id": "tu_1", "name": "calculator", "input": {"expression": "2+2"}}
            ],
        )
        msgs = history.to_messages()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "让我算一下。"
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) == 1
        assert msg["tool_calls"][0]["type"] == "function"
        assert msg["tool_calls"][0]["function"]["name"] == "calculator"
        # 参数应为 JSON 字符串
        assert "2+2" in msg["tool_calls"][0]["function"]["arguments"]

    def test_append_tool_result(self):
        history = ConversationHistory()
        history.append_tool_result("tu_1", "4")
        msgs = history.to_messages()
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["tool_call_id"] == "tu_1"
        assert msgs[0]["content"] == "4"

    def test_full_conversation_flow(self):
        history = ConversationHistory()
        history.append_user_message("2+2 等于多少？")
        history.append_assistant_message(
            text=None,
            tool_uses=[
                {"id": "tu_1", "name": "calculator", "input": {"expression": "2+2"}}
            ],
        )
        history.append_tool_result("tu_1", "4")
        history.append_assistant_message(text="答案是 4。")

        msgs = history.to_messages()
        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"  # 带 tool_calls
        assert msgs[2]["role"] == "tool"  # 工具结果
        assert msgs[3]["role"] == "assistant"  # 最终回复

    def test_clear(self):
        history = ConversationHistory()
        history.append_user_message("测试")
        history.clear()
        assert len(history) == 0

    def test_estimated_tokens(self):
        history = ConversationHistory()
        history.append_user_message("你好 " * 100)  # 300 个字符
        tokens = history.estimated_tokens()
        # 粗略估算: 4 个字符 ≈ 1 个 token
        assert 50 < tokens < 150

    def test_trim_to(self):
        history = ConversationHistory()
        for i in range(20):
            history.append_user_message(f"消息 {i} " * 50)
            history.append_assistant_message(text=f"回复 {i} " * 50)

        original_len = len(history)
        removed = history.trim_to(max_tokens=500)
        assert removed >= 0
        assert len(history) <= original_len


class TestToolRegistryIntegration:
    @pytest.mark.asyncio
    async def test_multiple_tool_execution(self):
        registry = ToolRegistry()

        # 注册多个工具
        for name in ["add", "multiply"]:
            async def handler(**kwargs):
                return str(sum(kwargs.values())) if name == "add" else str(kwargs.values())

            registry.register(ToolDefinition(
                name=name,
                description=f"{name} 工具",
                parameters={"type": "object", "properties": {}},
                handler=handler,
                source="builtin",
            ))

        # 并发执行
        import asyncio
        results = await asyncio.gather(
            registry.execute("tu_1", "add", {"a": 1, "b": 2}),
            registry.execute("tu_2", "multiply", {"x": 3, "y": 4}),
        )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_tool_result_error_handling(self):
        registry = ToolRegistry()

        async def failing_handler(**kwargs):
            raise ValueError("无效输入")

        registry.register(ToolDefinition(
            name="failer",
            description="总是失败",
            parameters={},
            handler=failing_handler,
            source="builtin",
        ))

        result = await registry.execute("tu_1", "failer", {})
        assert result.is_error
        assert "无效输入" in str(result.output)


class TestOpenAIFormatConversion:
    def test_tool_to_openai_format(self):
        tool = ToolDefinition(
            name="test_tool",
            description="一个测试工具",
            parameters={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "第一个参数"}
                },
                "required": ["param1"],
            },
            handler=lambda **kw: "ok",
            source="builtin",
        )
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "test_tool"
        assert fmt["function"]["description"] == "一个测试工具"
        assert "parameters" in fmt["function"]
        assert fmt["function"]["parameters"]["required"] == ["param1"]

    def test_registry_to_openai_format(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="calc", description="计算器", parameters={},
            handler=lambda **kw: "0", source="builtin",
        ))
        registry.register(ToolDefinition(
            name="search", description="网页搜索", parameters={},
            handler=lambda **kw: "results", source="builtin",
        ))

        tools = registry.to_openai_format()
        assert len(tools) == 2
        assert all(t["type"] == "function" for t in tools)
        names = {t["function"]["name"] for t in tools}
        assert names == {"calc", "search"}
