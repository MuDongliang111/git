"""文件操作工具 — 读取、写入、列出文件。"""

from __future__ import annotations

import os
from pathlib import Path

from ..base import ToolDefinition

# 文件操作的默认工作目录
_DEFAULT_WORKSPACE = os.getcwd()


def _resolve_path(path: str, workspace: str | None = None) -> Path:
    """在工作目录内安全地解析路径。"""
    ws = Path(workspace or _DEFAULT_WORKSPACE).resolve()
    resolved = (ws / path).resolve()
    # 确保路径在工作目录内
    if not str(resolved).startswith(str(ws)):
        raise ValueError(f"路径 '{path}' 在工作目录之外")
    return resolved


# --- 文件读取 ---

_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "要读取的文件路径（相对于工作目录）",
        },
    },
    "required": ["path"],
}


async def _read_file(path: str) -> str:
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"文件未找到: {path}"
        if resolved.is_dir():
            return f"'{path}' 是一个目录，不是文件"
        content = resolved.read_text(encoding="utf-8")
        if len(content) > 10000:
            content = content[:10000] + "\n... （已截断）"
        return content
    except Exception as exc:
        return f"读取文件时出错: {exc}"


def build_file_read_tool() -> ToolDefinition:
    return ToolDefinition(
        name="file_read",
        description="读取文件内容。路径相对于工作目录。"
        "内容最多显示 10000 个字符。",
        parameters=_READ_SCHEMA,
        handler=_read_file,
        source="builtin",
    )


# --- 文件写入 ---

_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "写入文件的路径（相对于工作目录）",
        },
        "content": {
            "type": "string",
            "description": "要写入文件的内容",
        },
    },
    "required": ["path", "content"],
}


async def _write_file(path: str, content: str) -> str:
    try:
        resolved = _resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"文件已写入: {path}（{len(content)} 个字符）"
    except Exception as exc:
        return f"写入文件时出错: {exc}"


def build_file_write_tool() -> ToolDefinition:
    return ToolDefinition(
        name="file_write",
        description="将内容写入文件。必要时会创建父目录。"
        "路径相对于工作目录。需要用户确认。",
        parameters=_WRITE_SCHEMA,
        handler=_write_file,
        source="builtin",
        requires_confirmation=True,
    )


# --- 文件列表 ---

_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "要列出的目录路径（相对于工作目录，默认为 '.'）",
            "default": ".",
        },
    },
    "required": [],
}


async def _list_files(path: str = ".") -> str:
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"目录未找到: {path}"
        if not resolved.is_dir():
            return f"'{path}' 不是目录"

        items = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        lines = [f"'{path}' 的内容:"]
        for item in items:
            prefix = "📁" if item.is_dir() else "📄"
            size = ""
            if item.is_file():
                try:
                    size_bytes = item.stat().st_size
                    if size_bytes < 1024:
                        size = f" ({size_bytes}B)"
                    elif size_bytes < 1024 * 1024:
                        size = f" ({size_bytes / 1024:.1f}KB)"
                    else:
                        size = f" ({size_bytes / (1024 * 1024):.1f}MB)"
                except OSError:
                    pass
            lines.append(f"  {prefix} {item.name}{size}")
        return "\n".join(lines)
    except Exception as exc:
        return f"列出目录时出错: {exc}"


def build_file_list_tool() -> ToolDefinition:
    return ToolDefinition(
        name="file_list",
        description="列出指定路径（相对于工作目录）中的文件和目录。",
        parameters=_LIST_SCHEMA,
        handler=_list_files,
        source="builtin",
    )
