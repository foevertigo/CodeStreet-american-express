"""
config.py — Backend Configuration & Environment Settings
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    app_name: str = "AmEx AI Servicing Backend"
    environment: str = "development"
    debug: bool = True

    # LLM Settings
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")  # 'groq' or 'openai'
    model_name: str = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")  # groq default model
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")

    # Audit & Storage (matching audit_service settings)
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://postgres:postgres_password@localhost:5432/amex_agent_db"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
