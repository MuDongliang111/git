# 🤖 AI Agent

一个模块化的对话式 AI Agent，支持**工具调用**、**技能集成**和 **MCP（模型上下文协议）服务**。

基于 DeepSeek API 和 MCP Python SDK 构建。

## 功能特性

- **工具调用** — 内置工具：计算器、网页搜索、网页抓取、文件操作、日期时间
- **技能系统** — 可热加载的技能包，支持自定义提示词和工具
- **MCP 集成** — 连接外部 MCP 服务器以扩展能力
- **流式输出** — 实时文本和工具调用事件流
- **交互式 CLI** — 丰富的终端界面，支持斜杠命令
- **深度推理** — 支持 DeepSeek 思考模式和可配置的推理深度

## 快速开始

### 1. 安装

```bash
cd ai_agent
pip install -e ".[dev]"
```

### 2. 设置 API Key

在项目根目录创建 `.env` 文件：

```bash
echo 'DEEPSEEK_API_KEY=sk-...' > .env
```

或直接设置环境变量：

```bash
export DEEPSEEK_API_KEY="sk-..."
```

### 3. 运行

```bash
# 交互模式
ai-agent

# 使用自定义配置
ai-agent -c config/default.yaml --mcp config/mcp_servers.yaml

# 或作为模块运行
python -m ai_agent.cli.main
```

## 命令列表

| 命令 | 描述 |
|---------|-------------|
| `/help` | 显示可用命令 |
| `/tools [query]` | 列出/搜索已注册的工具 |
| `/skills` | 显示已加载的技能 |
| `/skill activate <name>` | 激活一个技能 |
| `/skill deactivate <name>` | 停用一个技能 |
| `/mcp` | 显示 MCP 服务器状态 |
| `/config` | 显示当前配置 |
| `/clear` | 清除对话历史 |
| `/quit` | 退出 |

## 架构

```
CLI (src/ai_agent/cli/)
    ↓
Agent 核心 (src/ai_agent/agent/)
    ↓
┌─────────────┬──────────────┬──────────────┐
│  工具        │  技能        │  MCP         │
│  builtin/   │  manager.py  │  manager.py  │
│  registry   │  loader.py   │  translator  │
└─────────────┴──────────────┴──────────────┘
    ↓
SDK 层 (OpenAI + DeepSeek + MCP)
    ↓
配置 (src/ai_agent/config/)
```

## 添加新技能

1. 在 `skills/` 目录下创建文件夹：
   ```
   skills/my_skill/
   ├── skill.yaml
   ├── prompt.md
   └── tools.py  (可选)
   ```

2. `skill.yaml`：
   ```yaml
   name: my_skill
   version: "1.0.0"
   description: "这个技能的功能描述"
   requires_tools:
     - web_search
   ```

3. `prompt.md`：
   ```markdown
   ## 我的技能
   你现在扮演一个...
   ```

4. 加载并激活：
   ```
   /skill activate my_skill
   ```

## 配置说明

配置从 YAML 文件加载（后加载的文件会覆盖先加载的文件）：

```yaml
agent:
  model: "deepseek-v4-pro"
  max_tokens: 4096
  max_tool_rounds: 10
  reasoning_effort: "high"    # DeepSeek 推理深度
  thinking: true              # 启用思考模式

tools:
  enabled:
    - calculator
    - web_search
    - file_read
    - file_write

mcp_servers:
  - name: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"]
```

## 依赖项

- `openai>=1.0.0` — OpenAI SDK（用于调用 DeepSeek API）
- `python-dotenv>=1.0.0` — 环境变量管理
- `mcp>=1.0.0` — MCP Python SDK
- `pyyaml>=6.0` — YAML 配置解析
- `pydantic>=2.0` — 配置验证
- `httpx>=0.27.0` — 工具 HTTP 客户端
- `rich>=13.0.0` — 终端格式化输出
- `click>=8.0` — CLI 框架
