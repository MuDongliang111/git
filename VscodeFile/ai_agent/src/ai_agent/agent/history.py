"""Agent 的对话历史管理（OpenAI 消息格式）。"""

from __future__ import annotations

import json
from typing import Any


class ConversationHistory:
    """管理 OpenAI API 调用的消息列表。

    处理用户消息、助手回复（含可选的工具调用）和工具结果的追加，
    格式遵循 OpenAI Chat Completions API 规范。
    同时提供粗略的 token 估算和裁剪功能。
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # 追加方法
    # ------------------------------------------------------------------

    def append_user_message(self, text: str) -> None:
        """向历史中添加一条用户消息。"""
        self._messages.append({
            "role": "user",
            "content": text,
        })

    def append_assistant_message(
        self,
        text: str | None = None,
        tool_uses: list[dict[str, Any]] | None = None,
    ) -> None:
        """添加一条助手消息，可选带工具调用。

        Parameters
        ----------
        text : str | None
            文本内容（如果只有工具调用则可为空）。
        tool_uses : list[dict] | None
            工具调用列表（id, name, input）。
        """
        if tool_uses:
            tool_calls = [
                {
                    "id": tu["id"],
                    "type": "function",
                    "function": {
                        "name": tu["name"],
                        "arguments": (
                            tu["input"]
                            if isinstance(tu["input"], str)
                            else json.dumps(
                                tu["input"], ensure_ascii=False
                            )
                        ),
                    },
                }
                for tu in tool_uses
            ]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            msg["tool_calls"] = tool_calls
            self._messages.append(msg)
        else:
            self._messages.append({
                "role": "assistant",
                "content": text or "",
            })

    def append_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False
    ) -> None:
        """添加一条工具结果消息。

        使用 ``role="tool"`` 并关联对应的 ``tool_call_id``。
        """
        msg: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": tool_use_id,
            "content": content,
        }
        self._messages.append(msg)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def to_messages(self) -> list[dict[str, Any]]:
        """返回 OpenAI API 格式的消息列表（不含 system 消息）。"""
        return list(self._messages)

    def estimated_tokens(self) -> int:
        """粗略的 token 估算（4 个字符 ≈ 1 个 token）。"""
        total_chars = 0
        for msg in self._messages:
            total_chars += len(str(msg.get("content", "")))
        return max(1, total_chars // 4)

    def __len__(self) -> int:
        return len(self._messages)

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    def trim_to(self, max_tokens: int) -> int:
        """删除最早的消息，直到预估 token 数 ≤ *max_tokens*。

        返回移除的消息数量。
        """
        removed = 0
        while len(self._messages) > 2 and self.estimated_tokens() > max_tokens:
            self._messages.pop(0)
            removed += 1
            # 确保不会孤立 tool 消息（没有对应的 assistant 消息）
            if self._messages and self._messages[0].get("role") == "tool":
                self._messages.pop(0)
                removed += 1
        return removed

    def clear(self) -> None:
        """重置对话记录。"""
        self._messages.clear()

    def last_message(self) -> dict[str, Any] | None:
        """返回最近的一条消息，或 None。"""
        return self._messages[-1] if self._messages else None
