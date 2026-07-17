"""POST /api/chat/stream：把 LLM 流式输出转成 SSE。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import openai
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.prompts import DEFAULT_SYSTEM_PROMPT
from app.services import llm_service

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


# 开发演示用预设内容：含说明文字 / 三种对齐的表格 / 中英混排 / 列表 / 代码块。
# 用于在无 API Key 时也能验证前端流式表格渲染效果。
MOCK_CONTENT = """下面是 **北京 / 上海 / 深圳** 三座城市的经济指标对比：

| 城市 | GDP（万亿元） | 平均薪资（元/月） | 房价（万元/㎡） | 区域 |
| :--- | ---: | ---: | ---: | :---: |
| 北京 Beijing | 4.3 | 18700 | 6.2 | 北方 |
| 上海 Shanghai | 4.7 | 17900 | 5.8 | 东方 |
| 深圳 Shenzhen | 3.4 | 16500 | 7.0 | 南方 |

要点：

- 上海 GDP 总量最高
- 深圳房价最高，房价收入比也偏高
- 三城平均薪资均超过 1.6 万元/月

示例代码：

```python
cities = ["北京", "上海", "深圳"]
for city in cities:
    print(city)
```
"""


async def _mock_iterate() -> AsyncIterator[str]:
    """逐字推送预设内容，模拟真实流式（无需 API Key）。"""
    if settings.llm_mock_delay > 0:
        await asyncio.sleep(settings.llm_mock_delay)
    for ch in MOCK_CONTENT:
        yield ch
        await asyncio.sleep(0.012)


def _sse(payload: dict[str, Any] | str) -> str:
    """封装一条 SSE 数据：data: <json 或 [DONE]>\n\n。"""
    body = "[DONE]" if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f"data: {body}\n\n"


def _build_messages(req: ChatRequest) -> list[dict[str, str]]:
    """拼装最终发给 LLM 的消息列表：若无 system 则注入默认表格 prompt。"""
    messages = [m.model_dump() for m in req.messages]
    if not any(m["role"] == "system" for m in messages):
        system = settings.system_prompt or DEFAULT_SYSTEM_PROMPT
        messages = [{"role": "system", "content": system}, *messages]
    return messages


async def _stream_sse(source: AsyncIterator[str]):
    """统一的 SSE 生成器：把任意 content 迭代器转成 SSE。

    流中途的错误以 SSE error 事件下发，前端据此显示友好提示；
    流启动前的错误（鉴权 / 限流 / 连接 / 超时）由调用方映射成 HTTP 状态码。
    """
    try:
        async for content in source:
            yield _sse({"content": content})
        yield _sse("[DONE]")
    except openai.APITimeoutError:
        yield _sse({"error": "LLM 响应超时（60s）。", "code": 504})
    except openai.APIConnectionError:
        yield _sse({"error": "无法连接 LLM 服务。", "code": 502})
    except openai.APIStatusError as exc:
        yield _sse({"error": f"LLM 服务错误：{exc.status_code}", "code": exc.status_code})
    except Exception as exc:  # noqa: BLE001 - SSE 流兜底，避免连接挂死
        yield _sse({"error": f"服务端内部错误：{type(exc).__name__}", "code": 500})


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # 禁用反向代理缓冲，确保 token 即时下发
    "Connection": "keep-alive",
}


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    # 1) 开发演示模式：无需 API Key，直接流式推送预设表格内容
    if settings.llm_mock:
        return StreamingResponse(
            _stream_sse(_mock_iterate()),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # 2) 未配置 key：以 HTTP 错误返回，前端走错误分支
    if not settings.llm_api_key:
        return JSONResponse(
            status_code=500,
            content={"error": "后端未配置 LLM_API_KEY，请在 backend/.env 中设置后重启服务。"},
        )

    # 3) 预检：在进入流之前建立连接，把鉴权 / 限流 / 连接 / 超时错误
    #    映射成标准 HTTP 状态码（契合验收标准：key 失效返回 401 等）。
    messages = _build_messages(req)
    try:
        stream = await llm_service.create_stream(messages, req.model, req.temperature)
    except openai.AuthenticationError:
        return JSONResponse(status_code=401, content={"error": "LLM_API_KEY 失效。"})
    except openai.RateLimitError:
        return JSONResponse(status_code=429, content={"error": "请求过于频繁或额度不足（Rate Limit）。"})
    except openai.APITimeoutError:
        return JSONResponse(status_code=504, content={"error": "LLM 响应超时（60s）。"})
    except openai.APIConnectionError:
        return JSONResponse(status_code=502, content={"error": "无法连接 LLM 服务。"})
    except openai.APIStatusError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": f"LLM 服务错误：{exc.status_code}"})

    return StreamingResponse(
        _stream_sse(llm_service.iterate_stream(stream)),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
