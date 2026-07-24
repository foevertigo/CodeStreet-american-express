"""
config.py — Centralized configuration for audit_service.

Reads all values from environment variables (set in .env).
Uses pydantic-settings for type-safe config with validation.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration values loaded from environment variables.

    These are automatically loaded from .env if you call:
        from audit_service.config import get_settings
        settings = get_settings()
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",              # Ignore extra env vars not defined here
    )

    # -------------------------------------------------------------------------
    # Kafka
    # -------------------------------------------------------------------------
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_producer_retries: int = 3
    kafka_producer_ack: str = "all"

    # Topic names — use these constants, not raw strings
    kafka_topic_agent_actions: str = "agent-actions"
    kafka_topic_compliance_decisions: str = "compliance-decisions"
    kafka_topic_card_events: str = "card-events"
    kafka_topic_system_errors: str = "system-errors"
    kafka_topic_escalations: str = "escalations"

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = "redis://:redis_secure_pass_2024@localhost:6379/0"
    redis_session_ttl_seconds: int = 1800  # 30 minutes

    # -------------------------------------------------------------------------
    # PostgreSQL
    # -------------------------------------------------------------------------
    postgres_dsn: str = "postgresql://amex_user:amex_secure_pass_2024@localhost:5432/amex_agent"

    # -------------------------------------------------------------------------
    # Elasticsearch
    # -------------------------------------------------------------------------
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "amex-audit"

    # -------------------------------------------------------------------------
    # General
    # -------------------------------------------------------------------------
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the global Settings singleton.
    Cached with lru_cache so .env is only read once per process.

    Usage:
        from audit_service.config import get_settings
        settings = get_settings()
        print(settings.kafka_bootstrap_servers)
    """
    return Settings()
