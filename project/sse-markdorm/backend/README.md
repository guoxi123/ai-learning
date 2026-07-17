# Backend — FastAPI

LLM 流式调用的 FastAPI 后端，把 LLM 的流式输出转成 SSE 推给前端。

## 启动

```bash
uv sync

# Mock 模式（无需 API Key，流式推送预设表格内容，用于演示 / 验证前端）
LLM_MOCK=true uv run uvicorn app.main:app --port 8000 --reload

# 真实 LLM：先在 .env 配置 LLM_API_KEY 且 LLM_MOCK=false
uv run uvicorn app.main:app --port 8000 --reload
```

健康检查：`GET http://localhost:8000/api/health`

## 环境变量（`.env`）

见 `.env.example`，核心项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_API_KEY` | （空） | DeepSeek / OpenAI / 通义 key |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 切换厂商改这里 |
| `LLM_MODEL` | `deepseek-chat` | 切换厂商改这里 |
| `LLM_MOCK` | `false` | `true` 时跳过真实 LLM，流式推送预设内容 |
| `PORT` | `8000` | 服务端口 |
| `REQUEST_TIMEOUT` | `60.0` | LLM 请求超时（秒） |
| `CORS_ORIGINS` | `[http://localhost:5173,...]` | 前端源白名单（JSON 数组） |

## API

### `POST /api/chat/stream`

**请求体**
```json
{
  "messages": [{ "role": "user", "content": "对比北京、上海、深圳的房价和薪资" }],
  "model": "deepseek-chat",
  "temperature": 0.3
}
```
若 `messages` 中没有 `system` 角色，后端会自动注入一段引导「优先用 Markdown 表格作答」的 system prompt（见 `app/prompts.py`）。

**响应**：`text/event-stream`
```
data: {"content":"下面"}

data: {"content":"是"}

...

data: [DONE]
```

**错误状态码**（流开始前的错误以标准 HTTP 状态码返回，流中途的错误以 SSE `error` 事件下发）：

| 情况 | 状态码 |
|---|---|
| 未配置 Key | 500 |
| Key 失效 | 401 |
| 限流 / 额度不足 | 429 |
| 响应超时（60s） | 504 |
| 无法连接 LLM | 502 |

## 关键文件

- `app/routes/chat.py` — 路由 + SSE 封装 + mock 模式 + 错误映射
- `app/services/llm_service.py` — `openai.AsyncOpenAI` 的 `stream=True` 封装
- `app/prompts.py` — 强制表格输出的 system prompt
