"""AgentCore — 对话和工具调用循环。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from ..tools.registry import ToolRegistry
from .events import (
    AgentEvent,
    ErrorEvent,
    TextDelta,
    ThinkingDelta,
    ThinkingEnd,
    ThinkingStart,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
    TurnStart,
)
from .history import ConversationHistory
from .llm import LLMClient

logger = logging.getLogger(__name__)


class AgentCore:
    """核心 Agent 循环。

    编排对话流程：接收用户消息，调用 LLM（携带可用工具），
    执行工具调用，将结果反馈给 LLM，重复直到 LLM 只返回文本
    或达到轮次上限。
    """

    def __init__(
        self,
        config,  # AgentConfig（延迟导入以避免循环引用）
        llm: LLMClient,
        tool_registry: ToolRegistry,
        skill_manager=None,
    ) -> None:
        self._config = config
        self._llm = llm
        self._tool_registry = tool_registry
        self._skill_manager = skill_manager
        self._history = ConversationHistory()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """处理一个用户轮次，产生事件流。

        用法::

            async for event in agent.run("2+2 等于多少?"):
                if isinstance(event, TextDelta):
                    print(event.text, end="", flush=True)
                elif isinstance(event, TurnComplete):
                    print(f"\\n完成 ({event.stop_reason})")
        """
        yield TurnStart(user_message=user_message)
        self._history.append_user_message(user_message)

        system_prompt = self._build_system_prompt()
        tools = self._build_tools()

        round_count = 0
        max_rounds = getattr(self._config, "max_tool_rounds", 10)
        reasoning_effort = getattr(self._config, "reasoning_effort", "high")
        thinking = getattr(self._config, "thinking", True)

        while round_count < max_rounds:
            text_buffer: list[str] = []
            # 工具调用累积：index -> {id, name, arguments_parts}
            tool_call_accum: dict[int, dict[str, Any]] = {}
            finalized_tool_uses: list[dict[str, Any]] = []
            thinking_started = False

            # --- 流式 LLM 响应 ---
            try:
                async for raw_chunk in self._llm.stream_message(
                    model=self._config.model,
                    system_prompt=system_prompt,
                    messages=self._history.to_messages(),
                    tools=tools,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    reasoning_effort=reasoning_effort,
                    thinking=thinking,
                ):
                    for event in self._process_raw_chunk(
                        raw_chunk,
                        text_buffer,
                        tool_call_accum,
                        finalized_tool_uses,
                        thinking_started,
                    ):
                        if isinstance(event, ThinkingStart):
                            thinking_started = True
                        yield event
            except Exception as exc:
                logger.exception("LLM 流式调用失败")
                yield ErrorEvent(message=str(exc), recoverable=False)
                return

            # --- 没有工具调用：本轮完成 ---
            if not finalized_tool_uses:
                full_text = "".join(text_buffer)
                self._history.append_assistant_message(text=full_text)
                yield TurnComplete(stop_reason="end_turn")
                return

            # --- 记录包含 tool_calls 的助手消息 ---
            self._history.append_assistant_message(
                text="".join(text_buffer) or None,
                tool_uses=finalized_tool_uses,
            )

            # --- 发出 ToolCallStart 事件 ---
            for tu in finalized_tool_uses:
                yield ToolCallStart(
                    tool_use_id=tu["id"],
                    tool_name=tu["name"],
                    params=tu["input"],
                )

            # --- 并发执行所有工具调用 ---
            results = await asyncio.gather(
                *[
                    self._tool_registry.execute(tu["id"], tu["name"], tu["input"])
                    for tu in finalized_tool_uses
                ]
            )

            # --- 发出 ToolCallEnd 事件并记录结果 ---
            for tu, result in zip(finalized_tool_uses, results):
                yield ToolCallEnd(
                    tool_use_id=tu["id"],
                    tool_name=tu["name"],
                    result=result,
                )
                self._history.append_tool_result(
                    tool_use_id=tu["id"],
                    content=str(result.output),
                    is_error=result.is_error,
                )

            round_count += 1

        # 超过最大轮次
        yield ErrorEvent(
            message=f"已达到最大工具调用轮次 ({max_rounds})，已停止。",
            recoverable=False,
        )

    def clear_history(self) -> None:
        """重置对话以开启新会话。"""
        self._history.clear()

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """组合完整系统提示词：基础提示 + 已激活的技能提示。"""
        prompt = self._config.system_prompt
        if self._skill_manager:
            skill_prompt = self._skill_manager.get_active_prompt()
            if skill_prompt:
                prompt += "\n\n" + skill_prompt
        return prompt

    def _build_tools(self) -> list[dict]:
        """获取当前工具的 OpenAI API 格式列表。"""
        return self._tool_registry.to_openai_format()

    def _process_raw_chunk(
        self,
        chunk: Any,
        text_buffer: list[str],
        tool_call_accum: dict[int, dict[str, Any]],
        finalized_tool_uses: list[dict[str, Any]],
        thinking_started: bool = False,
    ) -> list[AgentEvent]:
        """将 OpenAI 流式 chunk 转换为 AgentEvent 列表。

        处理增量文本、推理内容（DeepSeek thinking）和增量 tool_calls
        的累积。当 finish_reason 为 ``tool_calls`` 或 ``stop`` 时
        完成工具调用的解析。
        """
        events: list[AgentEvent] = []

        # -- 内部 _final 标记（来自 LLMClient） --
        chunk_type = getattr(chunk, "type", "")
        if chunk_type == "_final":
            return events

        # -- 检查是否为 dict 类型（某些 edge case） --
        if isinstance(chunk, dict):
            chunk_type = chunk.get("type", "")
            if chunk_type == "_final":
                return events

        # -- 获取 choices --
        choices = getattr(chunk, "choices", None)
        if not choices:
            return events

        for choice in choices:
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue

            # --- 处理推理内容（DeepSeek thinking） ---
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                if not thinking_started:
                    events.append(ThinkingStart())
                    thinking_started = True
                events.append(ThinkingDelta(text=reasoning))

            # --- 处理文本内容 ---
            content = getattr(delta, "content", None)
            if content:
                # 如果有 thinking 在进行，先结束它
                if thinking_started:
                    events.append(ThinkingEnd())
                    thinking_started = False
                text_buffer.append(content)
                events.append(TextDelta(text=content))

            # --- 处理增量 tool_calls ---
            tool_calls_delta = getattr(delta, "tool_calls", None)
            if tool_calls_delta:
                for tc_delta in tool_calls_delta:
                    idx = getattr(tc_delta, "index", 0)

                    # 初始化该 tool_call 的累积器
                    if idx not in tool_call_accum:
                        tool_call_accum[idx] = {
                            "id": "",
                            "name": "",
                            "arguments_parts": [],
                        }

                    acc = tool_call_accum[idx]

                    tc_id = getattr(tc_delta, "id", None)
                    if tc_id:
                        acc["id"] = tc_id

                    func = getattr(tc_delta, "function", None)
                    if func:
                        func_name = getattr(func, "name", None)
                        if func_name:
                            acc["name"] = func_name
                        func_args = getattr(func, "arguments", None)
                        if func_args:
                            acc["arguments_parts"].append(func_args)

            # --- 处理 finish_reason ---
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason:
                # 如果 thinking 还在进行，结束它
                if thinking_started:
                    events.append(ThinkingEnd())
                    thinking_started = False

                # 解析累积的工具调用
                for idx in sorted(tool_call_accum.keys()):
                    acc = tool_call_accum[idx]
                    if acc["id"] and acc["name"]:
                        raw_args = "".join(acc["arguments_parts"])
                        try:
                            parsed_input = json.loads(raw_args) if raw_args else {}
                        except json.JSONDecodeError:
                            logger.warning(
                                "无法解析 tool_call 的 arguments JSON: %s", raw_args
                            )
                            parsed_input = {}
                        finalized_tool_uses.append({
                            "id": acc["id"],
                            "name": acc["name"],
                            "input": parsed_input,
                        })

        return events
