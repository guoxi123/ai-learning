"""应用配置：从环境变量 / .env 读取。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 忽略 .env 里未声明的字段，避免多余变量导致启动失败
        extra="ignore",
    )

    # LLM 配置：默认 DeepSeek，切换 OpenAI / 通义只需改这三项
    # OpenAI:   https://api.openai.com/v1 + gpt-4o-mini
    # 通义千问:  https://dashscope.aliyuncs.com/compatible-mode/v1 + qwen-plus
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # 开发演示用：为 true 时跳过真实 LLM，直接流式推送预设表格内容（无需 key）
    llm_mock: bool = False
    # mock 首字延迟（秒）：用于测试前端的「无响应自动断开」逻辑（模拟 TTFB 慢）
    llm_mock_delay: float = 0.0

    # 服务
    port: int = 8000
    request_timeout: float = 60.0

    # CORS 白名单（.env 里写成 JSON 数组字符串）
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 可选：覆盖默认 system prompt
    system_prompt: str = ""


settings = Settings()
