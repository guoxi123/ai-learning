"""LLM 调用封装：基于 openai SDK 的流式接口（DeepSeek / OpenAI / 通义均兼容）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

# 全局复用同一个异步客户端（连接池）
_client = AsyncOpenAI(
    api_key=settings.llm_api_key or "missing-key",
    base_url=settings.llm_base_url,
    timeout=settings.request_timeout,
)


async def create_stream(
    messages: list[dict[str, Any]],
    model: str | None,
    temperature: float,
) -> Any:
    """建立流式连接并返回 stream 对象。

    鉴权 / 连接 / 超时类错误会在 await 这次调用时抛出，
    便于路由层把它们映射成对应的 HTTP 状态码（401 / 429 / 502 / 504）。
    """
    return await _client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )


async def iterate_stream(stream: Any) -> AsyncIterator[str]:
    """遍历流，逐个 yield 文本增量（content delta）。跳过空内容。"""
    async for chunk in stream:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield content
