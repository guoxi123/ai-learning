# ai-learning

AI / LLM 应用学习与实践仓库。下设若干**彼此独立、可单独运行**的子项目，每个切入一个具体的 AI 工程主题：从对话记忆管理、到 LLM 流式交互渲染、再到 Agent 编排。

## 仓库总览

```
ai-learning/
├── docs/                       学习笔记
│   └── agent-teams-vs-subagents.md
├── project/                    子项目（各自独立，无共享构建）
│   ├── memory/                 长对话上下文压缩
│   ├── sse-markdorm/           LLM 流式渲染
├── .gitignore                  仓库级通用忽略规则
└── README.md                   本文档
```

## 子项目

| 子项目 | 主题 | 技术栈 | 一句话说明 |
|---|---|---|---|
| [project/memory](project/memory/) | 长对话上下文压缩 | Python · MySQL | 原始消息永不丢失，以「原始表 + 压缩表 + 映射表 + 缓存表」四层架构实现可追溯、可版本化、分层的上下文压缩。详见 [TECH_DESIGN](project/memory/TECH_DESIGN.md) |
| [project/sse-markdorm](project/sse-markdorm/) | LLM 流式渲染 | React 19 · FastAPI · SSE · DeepSeek | 自然语言提问 → 后端调 LLM → 前端逐字流式渲染，重点解决 Markdown 表格在流式生长过程中的格式抖动与错位。详见 [README](project/sse-markdorm/README.md) |

各子项目的**安装与运行步骤各不相同**（依赖、端口、所需的 API Key 都不一样），请进入对应目录参阅其 README。

## 学习笔记

- [docs/agent-teams-vs-subagents.md](docs/agent-teams-vs-subagents.md) — Agent Teams 与 Subagents 的区别与选型
- [docs/sse-vs-websocket.md](docs/sse-vs-websocket.md) — SSE 与 WebSocket 实时推送选型
- [docs/rag-architecture.md](docs/rag-architecture.md) — 企业级 RAG 知识库架构设计

## 仓库约定

- **通用忽略规则**：根 [.gitignore](.gitignore) 覆盖 Python / Node / OS / IDE / 环境变量等通用产物；各子项目另有自己的 `.gitignore` 处理特有细节（如 `memory/` 完全依赖根级兜底）。
- **密钥与环境变量**：各项目用 `.env`（已被忽略）存放密钥，模板见对应目录的 `.env.example`，切勿提交真实 Key。
- **依赖管理**：Python 项目用 `uv` 或 `pip`（见各 `pyproject.toml` / `requirements.txt`），前端用 `pnpm` / `npm`；锁文件（`uv.lock` / `pnpm-lock.yaml` 等）纳入版本控制以保证可复现。
- **无顶层构建**：子项目之间没有共享的构建或启动入口，按需 `cd` 到对应目录单独运行。
