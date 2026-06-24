"""网页抓取工具 — 获取 URL 内容并转换为文本。"""

from __future__ import annotations

from ..base import ToolDefinition

_FETCH_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "要获取内容的 URL",
        },
    },
    "required": ["url"],
}


async def _fetch_url(url: str) -> str:
    """获取 URL 并返回其文本内容。"""
    import httpx
    import re

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "ai-agent/0.1.0"},
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/html" in content_type:
                # 简单的 HTML 转文本：去除标签
                text = resp.text
                text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
                text = text.strip()
                # 截断到合理的大小
                if len(text) > 8000:
                    text = text[:8000] + "\n... （已截断）"
                return text
            elif "text/" in content_type or "application/json" in content_type:
                text = resp.text
                if len(text) > 8000:
                    text = text[:8000] + "\n... （已截断）"
                return text
            else:
                return f"无法获取类型为 {content_type} 的内容"

    except httpx.HTTPStatusError as exc:
        return f"HTTP 错误 {exc.response.status_code}，URL: {url}"
    except Exception as exc:
        return f"抓取失败: {exc}"


def build_web_fetch_tool() -> ToolDefinition:
    return ToolDefinition(
        name="web_fetch",
        description="从 URL 获取内容并返回文本。会处理 HTML 页面，"
        "去除标签。内容最长截断到 8000 个字符。",
        parameters=_FETCH_SCHEMA,
        handler=_fetch_url,
        source="builtin",
    )
