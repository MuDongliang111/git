"""日期时间工具 — 当前时间和日期计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from ..base import ToolDefinition

_DATETIME_SCHEMA = {
    "type": "object",
    "properties": {
        "timezone": {
            "type": "string",
            "description": "时区名称（例如 'UTC'、'Asia/Shanghai'、'America/New_York'）。默认为本地时间。",
        },
        "format": {
            "type": "string",
            "description": "strftime 格式字符串。默认为 ISO 8601。",
        },
    },
    "required": [],
}


async def _get_datetime(timezone: str = "", format: str = "") -> str:
    """返回当前日期和时间，可选指定时区。"""
    try:
        if timezone:
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                return "错误: 时区支持需要 Python 3.9+ 及 zoneinfo 模块"
            tz = ZoneInfo(timezone)
        else:
            tz = None  # 本地时间

        now = datetime.now(tz)
        fmt = format or "%Y-%m-%dT%H:%M:%S.%f%z"
        if not format and tz is None:
            # 本地时间输出更简洁，不含时区偏移
            fmt = "%Y-%m-%d %H:%M:%S"

        formatted = now.strftime(fmt)
        day_of_week = now.strftime("%A")
        week_number = now.isocalendar()[1]
        timestamp = now.timestamp()

        return (
            f"当前时间: {formatted}\n"
            f"星期: {day_of_week}\n"
            f"周数: {week_number}\n"
            f"Unix 时间戳: {timestamp:.0f}"
        )
    except Exception as exc:
        return f"获取日期时间时出错: {exc}"


def build_datetime_tool() -> ToolDefinition:
    return ToolDefinition(
        name="datetime_now",
        description="获取当前日期和时间。支持时区指定"
        "（例如 'Asia/Shanghai'）和自定义 strftime 格式字符串。",
        parameters=_DATETIME_SCHEMA,
        handler=_get_datetime,
        source="builtin",
    )
