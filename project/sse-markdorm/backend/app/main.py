"""FastAPI 入口。"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes import chat

app = FastAPI(title="LLM Markdown 表格流式渲染器 - 后端")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "model": settings.llm_model, "base_url": settings.llm_base_url}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
