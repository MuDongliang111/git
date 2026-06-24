"""基于 OpenAI SDK 的 DeepSeek API 封装。"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """封装 ``openai.AsyncOpenAI``，用于调用 DeepSeek API 并流式返回消息。"""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise ValueError(
                "DEEPSEEK_API_KEY 未设置。请通过参数或 "
                "DEEPSEEK_API_KEY 环境变量提供。"
            )
        self._client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.deepseek.com",
        )

    @property
    def client(self) -> AsyncOpenAI:
        """返回 AsyncOpenAI 客户端。"""
        return self._client

    async def stream_message(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 1.0,
        reasoning_effort: str = "high",
        thinking: bool = True,
    ) -> AsyncIterator[Any]:
        """流式调用 DeepSeek API，逐块返回原始事件。

        Parameters
        ----------
        model : str
            模型 ID（例如 ``deepseek-v4-pro``）。
        system_prompt : str
            系统提示词。
        messages : list[dict]
            OpenAI 格式的对话历史。
        tools : list[dict]
            OpenAI 格式的工具定义（空列表表示不使用工具）。
        max_tokens : int
            最大输出 token 数。
        temperature : float
            采样温度。
        reasoning_effort : str
            DeepSeek 推理深度（``low``/``medium``/``high``/``xhigh``/``max``）。
        thinking : bool
            是否启用 DeepSeek 思考模式。

        Yields
        ------
        Any
            OpenAI 流式响应的原始 chunk 对象。
            最后一个事件为 ``{"type": "_final", "usage": ...}``。
        """
        # 构建完整的消息列表（包含系统提示词）
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            # DeepSeek 特有参数
            "extra_body": {
                "thinking": {"type": "enabled" if thinking else "disabled"},
                "reasoning_effort": reasoning_effort,
            },
        }

        # OpenAI 要求 tools 参数为非空列表时才传递
        if tools:
            kwargs["tools"] = tools

        logger.debug(
            "流式调用模型 model=%s, %d 个工具, reasoning_effort=%s",
            model,
            len(tools),
            reasoning_effort,
        )

        stream = await self._client.chat.completions.create(**kwargs)
        usage = None
        async for chunk in stream:
            # 收集 usage 信息（在最后一个 chunk 中）
            if hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            yield chunk

        # 返回汇总信息
        if usage:
            logger.debug("本轮完成: 用量=%s", usage)
        yield {"type": "_final", "usage": usage}
