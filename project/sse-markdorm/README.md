# LLM Markdown 表格流式渲染器

输入自然语言问题 → 后端调用 LLM → 前端逐字流式渲染，重点保证 **Markdown 表格在流式生长过程中格式完整、不闪烁、不乱码**，支持左 / 居中 / 右三种对齐，中英文混排不错位，表格 / 列表 / 代码块可混合渲染。

## 架构

```
浏览器(React) ──POST /api/chat/stream──▶ FastAPI ──stream=True──▶ LLM API(DeepSeek)
     ▲                                       │
     │ SSE: data:{"content":..} / [DONE]     │ openai SDK delta chunks
     └───────────────────────────────────────┘
```

API Key 只存在后端 `.env`，前端永不接触 —— 同时规避了「LLM API 不允许浏览器 CORS 直连」的问题（OpenAI / DeepSeek / 通义千问的 API 均不带 CORS 响应头，浏览器无法直连）。

## 技术栈

- **后端**：Python 3.13 · FastAPI · openai SDK(`stream=True`) · uv
- **前端**：React 19 · Vite · TypeScript · react-markdown + remark-gfm + remend · Tailwind v4
- **LLM**：DeepSeek（默认，可一键切 OpenAI / 通义千问）
- **通信**：SSE（Server-Sent Events）

## 快速开始

### 方式 A：Mock 模式（无需 API Key，立即看流式表格效果）

后端 `LLM_MOCK=true` 时跳过真实 LLM，逐字流式推送一段含**三种对齐表格 / 中英混排 / 列表 / 代码块**的预设内容，便于在没有 Key 时验证前端渲染。

```bash
# 后端
cd backend
uv sync
LLM_MOCK=true uv run uvicorn app.main:app --port 8000 --reload

# 前端（另开一个终端）
cd frontend
pnpm install
pnpm dev
# 浏览器打开 http://localhost:5173
```

### 方式 B：接入真实 LLM（以 DeepSeek 为例）

1. 在 https://platform.deepseek.com 申请 API Key
2. 编辑 `backend/.env`：
   ```env
   LLM_API_KEY=sk-你的key
   LLM_MOCK=false
   ```
3. 启动后端 `uv run uvicorn app.main:app --port 8000 --reload`，前端 `pnpm dev`

**切换 OpenAI / 通义千问**：只改 `.env` 的 `LLM_BASE_URL` + `LLM_MODEL`（三家都兼容 OpenAI 的 `/chat/completions` 流式协议）：

| 厂商 | LLM_BASE_URL | LLM_MODEL |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |

## 关键技术点（如何做到流式表格不闪烁）

| 难点 | 方案 |
|---|---|
| 表格分隔行 `\|---\|` 未到达时，`\|` 管道语法被当成普通段落裸露（业界称 FOIM） | 流式时用 **remend** 修补未完成的 markdown 块再交给 react-markdown 渲染 |
| 一条 SSE `data:{...}` 行可能被拆到两次网络读里，直接 `JSON.parse` 会失败 | `src/lib/sse.ts` **跨 read 行缓冲**，只处理以换行结尾的完整行 |
| 新数据行到达触发列宽 reflow 抖动 | CSS `table-layout: fixed`（列宽只由首行决定，后续行不重算） |
| react-markdown 每 token 重解析全文 | 组件 `memo`，content 不变的旧消息不重渲染 |
| 中英文混排撑破单元格 | `overflow-wrap` / `word-break: break-word` |
| API Key 泄露 / CORS | 全部经后端代理，前端同源访问 |

> 说明：最初选用了 Vercel 的 Streamdown（流式渲染库），实测发现其 table 解析器把 `:---:`（居中）误判为左对齐，不符合验收要求，故切回 `react-markdown + remark-gfm + remend` 组合 —— remark-gfm 对齐完全正确，remend 保证流式稳定性。

## 目录结构

```
├── backend/                 FastAPI 后端
│   ├── app/
│   │   ├── main.py          入口 + CORS
│   │   ├── routes/chat.py   POST /api/chat/stream（含 mock 模式）
│   │   ├── services/llm_service.py   openai SDK 流式封装
│   │   ├── core/config.py   环境变量
│   │   └── prompts.py       强制表格的 system prompt
│   └── .env.example
└── frontend/                React 前端
    └── src/
        ├── components/      Markdown / MessageItem / MessageList / ChatInput
        ├── hooks/useStreamChat.ts
        ├── lib/sse.ts
        ├── App.tsx          布局 + 明暗主题
        └── index.css        表格防抖 CSS + 主题令牌
```

## 验收对照

- ✅ 表格逐字流式展开，格式完整、无乱码
- ✅ 三种对齐：左 `:---` / 居中 `:---:` / 右 `---:`
- ✅ 中英文混排不错位（如「北京 Beijing」）
- ✅ 表格 / 列表 / 代码块混合渲染
- ✅ 滚动跟随（用户手动上滚时不抢滚动）
- ✅ 停止生成 / 60s 无数据超时 / 断线重试
- ✅ API Key 失效 → 后端 401 → 前端友好提示
- ✅ 多轮历史保留 / 新建对话清空
- ✅ 明暗主题切换
