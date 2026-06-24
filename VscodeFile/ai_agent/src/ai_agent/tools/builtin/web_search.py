"""网页搜索工具，使用 DuckDuckGo（无需 API Key）。"""

from __future__ import annotations

from ..base import ToolDefinition

_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索查询字符串",
        },
        "max_results": {
            "type": "integer",
            "description": "返回的最大结果数（默认 5，最大 10）",
            "default": 5,
        },
    },
    "required": ["query"],
}


async def _search_web(query: str, max_results: int = 5) -> str:
    """使用 DuckDuckGo 即时答案 API 搜索网页。"""
    import httpx

    max_results = min(max(1, max_results), 10)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 使用 DuckDuckGo 的即时答案 API（无需 API Key）
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
                headers={"User-Agent": "ai-agent/0.1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

            lines: list[str] = []
            heading = data.get("Heading", "")
            abstract = data.get("AbstractText", "")
            answer = data.get("Answer", "")

            if heading:
                lines.append(f"**{heading}**")
            if answer:
                lines.append(f"答案: {answer}")
            elif abstract:
                lines.append(abstract)
            else:
                # 回退到相关主题
                lines.append("未找到直接答案。相关主题:")
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    text = topic.get("Text", "")
                    url = topic.get("FirstURL", "")
                    if text:
                        lines.append(f"- {text}")
                        if url:
                            lines.append(f"  {url}")

            if not lines:
                lines.append(f"未找到与 '{query}' 相关的结果。")

            return "\n".join(lines)

    except Exception as exc:
        return f"搜索失败: {exc}"


def build_web_search_tool() -> ToolDefinition:
    return ToolDefinition(
        name="web_search",
        description="使用 DuckDuckGo 搜索网页。返回即时答案或相关主题。"
        "无需 API Key。适合事实性查询和定义查询。",
        parameters=_SEARCH_SCHEMA,
        handler=_search_web,
        source="builtin",
    )
