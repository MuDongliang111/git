# 🤖 AI Agent

<div align="center">

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](https://github.com/MuDongliang111/Ai-ChatAgent/releases)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek%20V4-purple.svg)](https://platform.deepseek.com/)

</div>

一个模块化的**对话式 AI Agent**，支持工具调用、技能热加载和 MCP（模型上下文协议）集成。

基于 **DeepSeek API** + **OpenAI SDK** + **MCP Python SDK** 构建，提供交互式命令行界面和流式事件系统。

---

## 📑 目录

- [功能特性](#-功能特性)
- [快速开始](#-快速开始)
- [项目架构](#-项目架构)
- [命令列表](#-命令列表)
- [配置说明](#-配置说明)
- [技能系统](#-技能系统)
- [MCP 集成](#-mcp-集成)
- [开发指南](#-开发指南)
- [版本历史](#-版本历史)

---

## ✨ 功能特性

| 模块 | 说明 |
|------|------|
| 🛠️ **工具调用** | 计算器、网页搜索（三引擎 fallback）、网页抓取、文件操作、日期时间 |
| 🧩 **技能系统** | 可热加载的技能包，支持自定义 prompt 和工具注入 |
| 🔌 **MCP 集成** | 连接外部 MCP 服务器，支持 stdio 传输协议 |
| 📡 **流式输出** | 实时文本和工具调用事件流，与渲染层完全解耦 |
| 💻 **交互式 CLI** | 基于 Rich 的终端界面，支持斜杠命令和彩色输出 |
| 🧠 **深度推理** | 支持 DeepSeek 思考模式（Thinking）和 5 级推理深度 |

---

## 🚀 快速开始

### 1. 环境要求

- Python >= 3.10
- DeepSeek API Key（[获取地址](https://platform.deepseek.com/api_keys)）

### 2. 安装

```bash
# 克隆仓库
git clone git@github.com:MuDongliang111/Ai-ChatAgent.git
cd Ai-ChatAgent/VscodeFile/ai_agent

# 安装依赖
pip install -e ".[dev]"
```

### 3. 配置 API Key

```bash
# 方式一：创建 .env 文件
echo 'DEEPSEEK_API_KEY=sk-your-key-here' > .env

# 方式二：设置环境变量
export DEEPSEEK_API_KEY="sk-your-key-here"
```

### 4. 启动

```bash
# 交互模式（默认配置）
ai-agent

# 指定配置文件
ai-agent -c config/default.yaml --mcp config/mcp_servers.yaml

# 调试模式
ai-agent -v
```

---

## 🏗️ 项目架构

```
src/ai_agent/
├── config/          # 配置系统 — YAML 加载 + Pydantic 验证 + 环境变量插值
│   ├── models.py    #   AppConfig / AgentConfig / MCPServerConfig
│   └── loader.py    #   深度合并 + ${VAR} 插值
│
├── tools/           # 工具系统 — 统一 ToolDefinition + 中央调度
│   ├── base.py      #   ToolDefinition / ToolResult
│   ├── registry.py  #   ToolRegistry — 注册/搜索/执行
│   └── builtin/     #   6 个内置工具
│
├── agent/           # 核心循环 — 事件驱动的对话引擎
│   ├── core.py      #   AgentCore — LLM ↔ 工具 循环
│   ├── events.py    #   12 种流式事件类型
│   ├── history.py   #   对话历史（OpenAI 格式）
│   ├── llm.py       #   DeepSeek API 封装
│   └── app.py       #   DI 容器 — 组件组装 + 生命周期
│
├── skills/          # 技能系统 — 热加载 prompt + 工具
│   ├── definition.py #  SkillDefinition 数据结构
│   ├── loader.py    #   动态导入 skills/tools.py
│   ├── manager.py   #   加载/激活/停用 生命周期
│   └── repository.py #  磁盘扫描发现
│
├── mcp/             # MCP 集成 — 外部工具服务器
│   ├── client_manager.py  # 连接/发现/调用/断开
│   └── tool_translator.py # MCP 工具 → ToolDefinition
│
└── cli/             # 交互界面 — Rich 终端 + 事件渲染
    └── main.py      #   Click 入口 + AgentREPL
```

**数据流：**

```
用户输入 → CLI → AgentCore.run()
                    │
            ┌───────▼────────┐
            │  LLM 调用       │ ← LLMClient.stream_message()
            │  (携带工具列表)  │    发送到 DeepSeek API
            └───────┬────────┘
                    │ 流式事件 (TextDelta / ToolCallStart / ...)
            ┌───────▼────────┐
            │  有 tool_calls? │
            └───┬───────┬────┘
           Yes   │       │   No → 返回文本 → TurnComplete
            ┌────▼────┐  │
            │ 执行工具 │  │ ← ToolRegistry.execute()
            │ (并发)   │  │    asyncio.gather
            └────┬────┘  │
                 │ 工具结果追加到对话历史
                 └──→ 循环回到 LLM 调用 ──→
```

---

## 📋 命令列表

| 命令 | 描述 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/tools [query]` | 列出/搜索已注册的工具 |
| `/skills` | 显示已加载技能及其状态 |
| `/skill activate <name>` | 激活指定技能 |
| `/skill deactivate <name>` | 停用指定技能 |
| `/mcp` | 显示 MCP 服务器连接状态 |
| `/config` | 显示当前配置详情 |
| `/clear` | 清除对话历史 |
| `/quit`, `/exit`, `/q` | 退出程序 |

---

## ⚙️ 配置说明

配置文件按顺序加载，后面的覆盖前面的（深度合并）。

```yaml
# config/default.yaml
agent:
  model: "deepseek-v4-pro"     # 模型 ID
  max_tokens: 4096             # 最大输出 token
  max_tool_rounds: 20          # 每轮最大工具调用次数
  temperature: 1.0             # 采样温度 (0.0-2.0)
  reasoning_effort: "high"     # 推理深度: low/medium/high/xhigh/max
  thinking: true               # 启用思考模式
  system_prompt: |             # 基础系统提示词
    你是一个可以使用工具的 AI 助手...

tools:
  enabled:                     # 启用的工具列表
    - calculator
    - web_search
    - web_fetch
    - file_read
    - file_write
    - file_list
    - datetime_now
  confirm:                     # 执行前需确认的工具
    - file_write

skills_dir: "./skills"         # 技能包目录
skills:                        # 自动激活的技能
  - code_reviewer
  - web_researcher
  - pptx_reader
tool_timeout: 30.0             # 工具执行超时(秒)
```

---

## 🧩 技能系统

技能是**可热加载的能力扩展包**，无需修改核心代码即可增强 Agent 能力。

### 技能目录结构

```
skills/my_skill/
├── skill.yaml     # 元数据 + 依赖声明
├── prompt.md      # 系统提示词片段（注入给 LLM）
└── tools.py       # （可选）自定义工具函数
```

### 已内置的技能

| 技能 | 描述 | 依赖工具 |
|------|------|----------|
| `code_reviewer` | 代码审查：Bug、安全、风格、性能 | `file_read`, `file_list` |
| `web_researcher` | 深度网页研究：搜索+抓取+综合 | `web_search`, `web_fetch` |
| `pptx_reader` | PPTX 文件读取与解析 | — |

### 创建自定义技能

1. 在 `skills/` 下创建目录：
   ```
   skills/my_skill/
   ├── skill.yaml
   ├── prompt.md
   └── tools.py      # 可选
   ```

2. 编写 `skill.yaml`：
   ```yaml
   name: my_skill
   version: "1.0.0"
   description: "我的自定义技能"
   requires_tools:
     - web_search
   ```

3. 编写 `prompt.md`：
   ```markdown
   ## 我的技能
   你现在扮演一个...
   在执行任务时请遵循以下规则:
   1. ...
   ```

4. 加载并激活：
   ```
   /skill activate my_skill
   ```

---

## 🔌 MCP 集成

MCP（Model Context Protocol）允许 Agent 连接外部工具服务器。

```yaml
# config/mcp_servers.yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/tmp/mcp-workspace"
    transport: stdio
    auto_connect: false
```

MCP 工具注册后命名规则：`mcp.{服务器名}.{工具名}`（如 `mcp.filesystem.read_file`），与内置工具统一调度。

---

## 🔧 开发指南

### 运行测试

```bash
# 运行所有测试
pytest

# 仅单元测试
pytest tests/unit/

# 带覆盖率
pytest --cov=src/ai_agent
```

### 项目依赖

| 依赖 | 用途 |
|------|------|
| `openai>=1.0.0` | OpenAI SDK（用于调用 DeepSeek API） |
| `mcp>=1.0.0` | MCP Python SDK |
| `rich>=13.0.0` | 终端格式化输出 |
| `click>=8.0` | CLI 框架 |
| `pyyaml>=6.0` | YAML 配置解析 |
| `pydantic>=2.0` | 配置数据验证 |
| `httpx>=0.27.0` | 异步 HTTP 客户端 |
| `python-dotenv>=1.0.0` | 环境变量管理 |
| `python-pptx>=0.6.21` | PPTX 文件解析 |

---

## 📝 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| [v0.2.0](https://github.com/MuDongliang111/Ai-ChatAgent/releases/tag/v0.2.0) | 2026-06-25 | 核心循环优化、多引擎搜索 fallback、网页抓取增强、pptx_reader 技能 |
| [v0.1.0](https://github.com/MuDongliang111/Ai-ChatAgent/releases/tag/v0.1.0) | 2026-06-24 | 初始版本：对话智能体、工具调用、技能系统、MCP 集成 |

---

## 📄 开源协议

MIT License — 详见 [LICENSE](LICENSE) 文件。
