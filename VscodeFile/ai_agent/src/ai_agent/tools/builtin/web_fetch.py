"""网页抓取工具 — 获取 URL 内容并转换为文本。

特性：
- 自动重试（最多 2 次），指数退避
- 多 User-Agent 轮换，避免被反爬
- HTML 正文提取，去除导航/广告/脚本等噪音
- 支持常见国内网站的抓取
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..base import ToolDefinition

logger = logging.getLogger(__name__)

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

# 轮换 User-Agent 列表，减少被屏蔽概率
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    ),
]

# 无意义标签/属性，提取正文时跳过
_REMOVE_TAGS = re.compile(
    r"</?(?:script|style|nav|footer|header|aside|noscript|iframe|svg|canvas"
    r"|meta|link|form|input|button|select|option|textarea)[^>]*>",
    re.DOTALL | re.IGNORECASE,
)

# 匹配空白行
_BLANK_LINE = re.compile(r"\n{3,}")


async def _fetch_url(url: str) -> str:
    """获取 URL 并返回文本内容。支持重试和 UA 轮换。"""
    import httpx

    max_retries = 2
    last_error = ""

    for attempt in range(max_retries + 1):
        ua = _USER_AGENTS[attempt % len(_USER_AGENTS)]

        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=True, http2=False
            ) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept": (
                            "text/html,application/xhtml+xml,"
                            "application/xml;q=0.9,image/webp,*/*;q=0.8"
                        ),
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate",
                        "DNT": "1",
                        "Connection": "keep-alive",
                    },
                )
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "").lower()

                if "text/html" in content_type:
                    text = _extract_text_from_html(resp.text)
                    return _truncate(text, 8000)

                elif "text/" in content_type or "application/json" in content_type:
                    text = resp.text
                    return _truncate(text, 8000)

                else:
                    return f"暂不支持抓取类型为 '{content_type}' 的内容"

        except httpx.ConnectTimeout:
            last_error = f"连接超时: {url}"
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
        except httpx.ReadTimeout:
            last_error = f"读取超时: {url}"
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # 429/503 等可重试的状态码
            if status in (429, 503, 502, 504) and attempt < max_retries:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            return f"HTTP 错误 {status}，URL: {url}"
        except httpx.ConnectError:
            last_error = f"无法连接到 {url}"
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
        except Exception as exc:
            last_error = f"抓取失败: {exc}"
            if attempt < max_retries:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

    return f"抓取失败（已重试 {max_retries} 次）: {last_error}"


# 正文容器选择器（按优先级排列）
_CONTENT_SELECTORS = [
    # 语义标签 — 最可靠
    r'<main[^>]*>(.*?)</main>',
    r'<article[^>]*>(.*?)</article>',
    # 常见正文 class/id
    r'<div[^>]*class="[^"]*(?:article|post-body|entry-content|markdown-body|post-content|doc-content|read-content)[^"]*"[^>]*>(.*?)</div>',
    r'<div[^>]*id="[^"]*(?:content|article|main|post|entry|read|doc)[^"]*"[^>]*>(.*?)</div>',
    r'<div[^>]*class="[^"]*(?:content|main|post|entry|detail|body|text)[^"]*"[^>]*>(.*?)</div>',
    r'<section[^>]*>(.*?)</section>',
]


def _plain_len(html_fragment: str) -> int:
    """估算 HTML 片段去除标签后的纯文本长度。"""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text)


def _find_content_candidates(cleaned_html: str) -> list[str]:
    """从 HTML 中提取所有可能的正文容器候选。"""
    candidates: list[str] = []
    for selector in _CONTENT_SELECTORS:
        for match in re.finditer(selector, cleaned_html, re.DOTALL | re.IGNORECASE):
            candidates.append(match.group(1))
    return candidates


def _pick_best_candidate(candidates: list[str], fallback_html: str) -> str:
    """从候选中选择最佳正文区域。

    规则：
    1. 优先语义标签（main/article），即使内容较少
    2. 其次选文本长度在 500-20000 之间的（太短是导航，太长是整个页面）
    3. 回退到 body 标签
    """
    scored: list[tuple[int, str]] = []

    for i, cand in enumerate(candidates):
        length = _plain_len(cand)
        # 打分：语义标签在前（candidates 按选择器顺序排列，前面的是语义标签）
        priority_bonus = max(0, 20 - i)  # 越靠前的选择器分越高
        # 长度得分：500-20000 区间最优
        if 500 <= length <= 20000:
            length_score = 30
        elif 200 <= length < 500:
            length_score = 15
        elif length > 20000:
            length_score = 5  # 太长可能是整页，降权
        else:
            length_score = 0
        scored.append((priority_bonus + length_score, cand))

    # 按得分降序排列
    scored.sort(key=lambda x: -x[0])

    if scored and scored[0][0] >= 15:
        return scored[0][1]

    # 没有好的候选，回退到 body
    body_match = re.search(
        r"<body[^>]*>(.*?)</body>", fallback_html, re.DOTALL | re.IGNORECASE
    )
    return body_match.group(1) if body_match else fallback_html


def _extract_text_from_html(html: str) -> str:
    """从 HTML 中提取有意义的正文文本。

    策略：
    1. 移除无意义标签（script, style, nav, footer 等）
    2. 尝试提取 <main>, <article> 或常见正文容器
    3. 回退到整个 <body>
    4. 去除 HTML 标签，压缩空白
    """
    # 移除无意义标签及其内容
    cleaned = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r"<noscript[^>]*>.*?</noscript>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    # 移除注释
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

    # 尝试提取正文区域
    # 策略：优先匹配语义标签，然后尝试常见内容容器，
    # 每个选择器取文本最长的匹配，第一个达到合理长度的就采用
    candidates = _find_content_candidates(cleaned)
    body_text = _pick_best_candidate(candidates, cleaned)


    # 移除剩余 HTML 标签，但保留块级元素换行
    body_text = re.sub(r"</?(?:p|div|h[1-6]|li|tr|br|hr|section|article)[^>]*>", "\n", body_text, flags=re.IGNORECASE)
    body_text = re.sub(r"<[^>]+>", " ", body_text)  # 其他标签变空格
    body_text = re.sub(r"&nbsp;", " ", body_text)
    body_text = re.sub(r"&amp;", "&", body_text)
    body_text = re.sub(r"&lt;", "<", body_text)
    body_text = re.sub(r"&gt;", ">", body_text)
    body_text = re.sub(r"&#x?[0-9a-f]+;", " ", body_text, flags=re.IGNORECASE)

    # 压缩空白
    body_text = re.sub(r"[ \t]+", " ", body_text)  # 同行空白合并
    body_text = _BLANK_LINE.sub("\n\n", body_text)  # 多余空行合并
    body_text = body_text.strip()

    return body_text


def _truncate(text: str, max_len: int) -> str:
    """截断文本到指定长度。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n... （内容已截断）"


def build_web_fetch_tool() -> ToolDefinition:
    return ToolDefinition(
        name="web_fetch",
        description=(
            "获取指定 URL 的网页内容并转换为纯文本。"
            "支持自动重试（最多 2 次）和 User-Agent 轮换，"
            "能智能提取正文（自动跳过导航、广告、脚本等）。"
            "内容最长 8000 字符。"
        ),
        parameters=_FETCH_SCHEMA,
        handler=_fetch_url,
        source="builtin",
    )
