#!/usr/bin/env python3
"""AI Agent 的交互式命令行界面。

用法::

    python -m ai_agent.cli.main                         # 使用 config/default.yaml
    python -m ai_agent.cli.main -c config/custom.yaml   # 自定义配置
    python -m ai_agent.cli.main --mcp config/mcp.yaml   # 带 MCP 服务器
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import click

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..agent.app import AgentApp
from ..agent.events import (
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

console = Console()
logger = logging.getLogger(__name__)


def _auto_load_dotenv() -> None:
    """自动加载项目目录下的 .env 文件。"""
    try:
        from dotenv import load_dotenv
        # 从当前目录向上查找 .env
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


# ------------------------------------------------------------------
# 事件渲染器
# ------------------------------------------------------------------


class EventRenderer:
    """使用 rich 格式化将 Agent 事件渲染到终端。"""

    def __init__(self) -> None:
        self._thinking = False
        self._tool_calls_in_progress: dict[str, str] = {}

    def render(self, event) -> None:
        """渲染单个 Agent 事件。"""
        if isinstance(event, TurnStart):
            pass  # 用户消息已由 REPL 回显

        elif isinstance(event, ThinkingStart):
            self._thinking = True
            console.print("[dim]🤔 思考中...[/dim]", end="")

        elif isinstance(event, ThinkingDelta):
            pass  # 不渲染思考增量（过于冗长）

        elif isinstance(event, ThinkingEnd):
            self._thinking = False

        elif isinstance(event, TextDelta):
            console.print(event.text, end="", highlight=False)

        elif isinstance(event, ToolCallStart):
            self._tool_calls_in_progress[event.tool_use_id] = event.tool_name
            console.print()
            console.print(
                f"  [bold cyan]🔧 {event.tool_name}[/bold cyan]",
                end=" ",
                highlight=False,
            )
            # 内联显示参数
            params_str = ", ".join(
                f"{k}={repr(v)[:40]}" for k, v in event.params.items()
            )
            if params_str:
                console.print(f"[dim]({params_str})[/dim]", highlight=False)

        elif isinstance(event, ToolCallEnd):
            name = self._tool_calls_in_progress.pop(event.tool_use_id, "")
            if event.result.is_error:
                console.print(
                    f"  [bold red]❌ {name} 失败:[/bold red] {event.result.output}",
                    highlight=False,
                )
            else:
                output_preview = str(event.result.output)[:200]
                console.print(
                    f"  [bold green]✅ {name}[/bold green] "
                    f"[dim]({event.result.elapsed_ms:.0f}ms)[/dim]",
                    highlight=False,
                )
                if len(str(event.result.output)) > 200:
                    output_preview += "..."

        elif isinstance(event, TurnComplete):
            console.print()

        elif isinstance(event, ErrorEvent):
            icon = "⚠️" if event.recoverable else "❌"
            console.print(f"\n  [bold red]{icon} {event.message}[/bold red]")


# ------------------------------------------------------------------
# REPL 循环
# ------------------------------------------------------------------


class AgentREPL:
    """AI Agent 的读取-求值-打印循环。"""

    def __init__(self, app: AgentApp) -> None:
        self.app = app
        self.renderer = EventRenderer()

    async def run(self) -> None:
        """启动交互式 REPL。"""
        console.print()
        console.print(
            Panel.fit(
                "[bold]🤖 AI Agent[/bold]\n"
                f"模型: [cyan]{self.app.config.agent.model}[/cyan]\n"
                f"工具: [green]{self.app.tool_registry.count()}[/green] | "
                f"技能: [yellow]{len(self.app.skill_manager.list_active())}[/yellow] | "
                f"MCP: [magenta]{len(self.app.mcp_manager.list_servers())}[/magenta]\n\n"
                "输入 [bold]/help[/bold] 查看命令，[bold]/quit[/bold] 退出",
                title="欢迎",
                border_style="blue",
            )
        )

        while True:
            try:
                user_input = console.input("\n[bold green]You ›[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]再见！[/dim]")
                break

            if not user_input:
                continue

            # 处理斜杠命令
            if user_input.startswith("/"):
                result = await self._handle_command(user_input)
                if result == "quit":
                    break
                continue

            # 处理用户消息
            console.print()
            console.print("[bold blue]Agent ›[/bold blue] ", end="")
            try:
                async for event in self.app.agent.run(user_input):
                    self.renderer.render(event)
            except Exception as exc:
                console.print(f"\n[bold red]错误: {exc}[/bold red]")
                logger.exception("Agent 运行失败")

    # ------------------------------------------------------------------
    # 命令处理
    # ------------------------------------------------------------------

    async def _handle_command(self, cmd: str) -> str | None:
        """处理斜杠命令。返回 'quit' 表示退出 REPL。"""
        parts = cmd.split()
        command = parts[0].lower()

        if command in ("/quit", "/exit", "/q"):
            console.print("[dim]再见！[/dim]")
            return "quit"

        elif command == "/help":
            self._show_help()

        elif command == "/clear":
            self.app.agent.clear_history()
            console.print("[dim]对话历史已清除。[/dim]")

        elif command == "/tools":
            self._show_tools(parts[1:])

        elif command == "/skills":
            self._show_skills()

        elif command == "/skill":
            await self._manage_skill(parts[1:])

        elif command == "/mcp":
            self._show_mcp()

        elif command == "/config":
            self._show_config()

        else:
            console.print(f"[red]未知命令: {command}[/red]")
            console.print("[dim]输入 /help 查看可用命令。[/dim]")

        return None

    def _show_help(self) -> None:
        """显示可用命令。"""
        table = Table(title="可用命令", border_style="blue")
        table.add_column("命令", style="cyan", no_wrap=True)
        table.add_column("描述")

        commands = [
            ("/help", "显示此帮助信息"),
            ("/quit, /exit, /q", "退出 Agent"),
            ("/clear", "清除对话历史"),
            ("/tools [query]", "列出所有工具，或按关键词搜索"),
            ("/skills", "列出已加载的技能及其状态"),
            ("/skill activate <name>", "激活一个技能"),
            ("/skill deactivate <name>", "停用一个技能"),
            ("/mcp", "显示 MCP 服务器状态"),
            ("/config", "显示当前配置"),
        ]
        for cmd, desc in commands:
            table.add_row(cmd, desc)

        console.print(table)

    def _show_tools(self, args: list[str]) -> None:
        """列出所有已注册工具，可选过滤。"""
        query = args[0] if args else ""
        tools = self.app.tool_registry.search(query) if query else self.app.tool_registry.list_all()

        if not tools:
            console.print("[dim]未找到工具。[/dim]")
            return

        table = Table(title=f"工具 ({len(tools)})", border_style="green")
        table.add_column("名称", style="cyan", no_wrap=True)
        table.add_column("来源", style="yellow")
        table.add_column("描述")

        for t in sorted(tools, key=lambda x: (x.source, x.name)):
            source_str = f"{t.source}"
            if t.source_name:
                source_str += f":{t.source_name}"
            table.add_row(t.name, source_str, t.description[:80])

        console.print(table)

    def _show_skills(self) -> None:
        """显示已加载的技能。"""
        skills = self.app.skill_manager.list_available()
        active = set(self.app.skill_manager.list_active())

        if not skills:
            console.print("[dim]未加载技能。[/dim]")
            return

        table = Table(title=f"技能 ({len(skills)})", border_style="yellow")
        table.add_column("名称", style="cyan", no_wrap=True)
        table.add_column("状态", style="green")
        table.add_column("描述")

        for name in sorted(skills):
            skill = self.app.skill_manager.get(name)
            status = "[green]● 已激活[/green]" if name in active else "[dim]○ 未激活[/dim]"
            desc = skill.description if skill else ""
            table.add_row(name, status, desc[:80])

        console.print(table)

    async def _manage_skill(self, args: list[str]) -> None:
        """激活或停用一个技能。"""
        if len(args) < 2:
            console.print("[red]用法: /skill <activate|deactivate> <name>[/red]")
            return

        action, name = args[0], args[1]

        try:
            if action == "activate":
                self.app.skill_manager.activate(name)
                console.print(f"[green]已激活技能: {name}[/green]")
            elif action == "deactivate":
                self.app.skill_manager.deactivate(name)
                console.print(f"[yellow]已停用技能: {name}[/yellow]")
            else:
                console.print(f"[red]未知操作: {action}。请使用 activate 或 deactivate。[/red]")
        except Exception as exc:
            console.print(f"[red]错误: {exc}[/red]")

    def _show_mcp(self) -> None:
        """显示 MCP 服务器状态。"""
        servers = self.app.mcp_manager.list_servers()

        if not servers:
            console.print("[dim]未连接 MCP 服务器。[/dim]")
            # 显示已配置但未连接的服务器
            if self.app.config.mcp_servers:
                console.print("\n[dim]已配置的服务器:[/dim]")
                for cfg in self.app.config.mcp_servers:
                    status = "[dim]未连接[/dim]"
                    if cfg.auto_connect:
                        status += " (已启用自动连接)"
                    console.print(f"  - {cfg.name}: {status}")
            return

        table = Table(title=f"MCP 服务器 ({len(servers)})", border_style="magenta")
        table.add_column("名称", style="cyan", no_wrap=True)
        table.add_column("工具数", style="green")
        table.add_column("状态", style="yellow")

        for name in sorted(servers):
            tool_count = len(self.app.tool_registry.names_by_source("mcp"))
            table.add_row(name, str(tool_count), "[green]已连接[/green]")

        console.print(table)

    def _show_config(self) -> None:
        """显示当前配置。"""
        cfg = self.app.config

        table = Table(title="配置", border_style="blue")
        table.add_column("设置项", style="cyan")
        table.add_column("值", style="green")

        table.add_row("模型", cfg.agent.model)
        table.add_row("最大 Token 数", str(cfg.agent.max_tokens))
        table.add_row("最大工具轮次", str(cfg.agent.max_tool_rounds))
        table.add_row("温度", str(cfg.agent.temperature))
        table.add_row("推理深度", cfg.agent.reasoning_effort)
        table.add_row("思考模式", "开启" if cfg.agent.thinking else "关闭")
        table.add_row("工具超时", f"{cfg.tool_timeout}s")
        table.add_row("技能目录", cfg.skills_dir)
        table.add_row("已启用工具", ", ".join(cfg.tools.enabled))
        table.add_row("需确认工具", ", ".join(cfg.tools.confirm))
        table.add_row("MCP 服务器数", str(len(cfg.mcp_servers)))

        console.print(table)


# ------------------------------------------------------------------
# Click CLI 入口
# ------------------------------------------------------------------


@click.command()
@click.option(
    "-c", "--config",
    "config_files",
    multiple=True,
    default=["config/default.yaml"],
    help="YAML 配置文件的路径（可重复使用）。",
    metavar="FILE",
)
@click.option(
    "--mcp",
    "mcp_config",
    default=None,
    help="MCP 服务器 YAML 文件的路径。",
    metavar="FILE",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="启用调试日志。",
)
def main(config_files: tuple[str, ...], mcp_config: str | None, verbose: bool) -> None:
    """AI Agent — 一个支持工具调用、技能系统和 MCP 集成的对话式 Agent。"""
    # 自动加载 .env
    _auto_load_dotenv()

    # 设置日志
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 收集配置文件
    all_configs = list(config_files)
    if mcp_config:
        all_configs.append(mcp_config)

    # 检查 API Key
    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print(
            "[bold red]错误:[/bold red] 未设置 DEEPSEEK_API_KEY 环境变量。\n"
            "[dim]请在 .env 文件中设置，或使用: export DEEPSEEK_API_KEY='sk-...'[/dim]"
        )
        sys.exit(1)

    # 构建并运行应用
    async def _run() -> None:
        app = AgentApp(*all_configs)
        try:
            await app.startup()
            repl = AgentREPL(app)
            await repl.run()
        finally:
            await app.shutdown()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
