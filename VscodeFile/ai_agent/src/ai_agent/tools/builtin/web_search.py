"""网页搜索工具，支持多引擎 fallback（国内可用）。

搜索链路：DuckDuckGo → Bing(cn.bing.com) → Sogou
一个引擎失败时自动切换到下一个，确保在国内外网络环境都可用。
"""

from __future__ import annotations

import re
import logging

from ..base import ToolDefinition

logger = logging.getLogger(__name__)

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


def _is_valid_result(result: str) -> bool:
    """检查搜索结果是否有效（包含实际链接或内容）。"""
    if not result:
        return False
    if result.startswith("搜索失败"):
        return False
    if result.startswith("所有搜索引擎"):
        return False
    # 必须包含至少一个链接或实质性内容
    if "http" in result or "答案:" in result:
        return True
    # 如果只有 "相关结果:" 这样的空标题，视为无效
    if len(result) < 50:
        return False
    # 至少包含一条有意义的行
    lines = [l for l in result.split("\n") if l.strip() and not l.startswith("**")]
    return len(lines) >= 2


async def _search_web(query: str, max_results: int = 5) -> str:
    """多引擎网页搜索，自动 fallback。

    依次尝试 DuckDuckGo、Bing(cn)、Sogou，返回第一个成功的结果。
    """
    import httpx

    max_results = min(max(1, max_results), 10)

    engines = [
        ("DuckDuckGo", _search_duckduckgo),
        ("Bing", _search_bing),
        ("Sogou", _search_sogou),
    ]

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for engine_name, engine_fn in engines:
            try:
                result = await engine_fn(client, query, max_results)
                # 有效结果必须：非空、包含实际链接或内容、非错误
                if _is_valid_result(result):
                    if engine_name != "DuckDuckGo":
                        result = f"[引擎: {engine_name}]\n{result}"
                    return result
                logger.debug("%s 返回无效结果（空或无效），尝试下一个引擎", engine_name)
            except Exception as exc:
                logger.debug("%s 搜索失败: %s，尝试下一个引擎", engine_name, exc)
                continue

    return f"所有搜索引擎均无法访问，请检查网络连接后重试。\n查询: {query}"


# =============================================================================
# 搜索引擎实现
# =============================================================================


async def _search_duckduckgo(
    client, query: str, max_results: int
) -> str:
    """DuckDuckGo 即时答案 API（无需 API Key，国外速度快）。"""
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
        topics = []
        for topic in data.get("RelatedTopics", [])[:max_results]:
            text = topic.get("Text", "")
            url = topic.get("FirstURL", "")
            if text:
                topics.append((text, url))

        if topics:
            lines.append("相关结果:")
            for text, url in topics:
                lines.append(f"- {text}")
                if url:
                    lines.append(f"  {url}")
        # 没有实际 topic 就不加"相关结果:"的空标题

    return "\n".join(lines) if len(lines) > 0 and any("http" in l or "答案" in l for l in lines) else ""


async def _search_bing(
    client, query: str, max_results: int
) -> str:
    """Bing 搜索（通过 cn.bing.com 抓取，国内可访问）。"""
    resp = await client.get(
        "https://cn.bing.com/search",
        params={"q": query, "count": max_results},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    resp.raise_for_status()
    return _parse_bing_results(resp.text, max_results)


async def _search_sogou(
    client, query: str, max_results: int
) -> str:
    """搜狗搜索（国内搜索引擎，通过网页抓取）。"""
    resp = await client.get(
        "https://www.sogou.com/web",
        params={"query": query, "num": max_results},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    resp.raise_for_status()
    return _parse_sogou_results(resp.text, max_results)


# =============================================================================
# 搜索结果解析
# =============================================================================


def _parse_bing_results(html: str, max_results: int) -> str:
    """解析 Bing 搜索结果页。"""
    # Bing 的搜索结果在 <li class="b_algo"> 中
    # 标题在 <h2><a> 中，摘要通常在后继元素中
    results = []
    pattern = re.compile(
        r'<li\s+class="b_algo"[^>]*>.*?<h2[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    matches = pattern.findall(html)

    for url, title in matches[:max_results]:
        title = re.sub(r"<[^>]+>", "", title).strip()
        if title and url:
            results.append(f"- [{title}]({url})")

    if not results:
        # 简化解析：直接找搜索结果链接
        link_pattern = re.compile(
            r'<a[^>]*href="(https?://(?!.*bing\.com)[^"]+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE,
        )
        seen = set()
        for url, text in link_pattern.findall(html):
            text = text.strip()
            url = url.replace("&amp;", "&")
            if text and url not in seen and len(text) > 5:
                seen.add(url)
                results.append(f"- [{text}]({url})")
            if len(seen) >= max_results:
                break

    return "\n".join(results) if results else ""


def _parse_sogou_results(html: str, max_results: int) -> str:
    """解析搜狗搜索结果页。"""
    results = []
    # 搜狗的结果在 class="vrwrap" 或 class="rb" 的 div 中
    # 尝试匹配标题链接
    pattern = re.compile(
        r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE,
    )
    seen = set()
    for url, text in pattern.findall(html):
        text = re.sub(r"<[^>]+>", "", text).strip()
        url = url.replace("&amp;", "&")
        # 过滤掉搜狗自身链接和过短的文本
        if (
            text
            and url not in seen
            and "sogou.com" not in url
            and len(text) > 8
        ):
            seen.add(url)
            results.append(f"- [{text[:80]}]({url})")
        if len(seen) >= max_results:
            break

    return "\n".join(results) if results else ""


def build_web_search_tool() -> ToolDefinition:
    return ToolDefinition(
        name="web_search",
        description=(
            "多引擎网页搜索，自动 fallback：DuckDuckGo → Bing(cn) → Sogou。"
            "在国内网络环境下自动切换到可用的搜索引擎。"
            "返回搜索结果链接和摘要。无需 API Key。"
        ),
        parameters=_SEARCH_SCHEMA,
        handler=_search_web,
        source="builtin",
    )
