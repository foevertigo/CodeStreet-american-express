"""
audit_service — FinTech AI Agent Async Audit Pipeline
======================================================

This package is the integration point for ALL teams.
It provides three clean interfaces:

1. Kafka Producer  → publish audit events to the event bus
2. Redis Client    → manage LangGraph conversation session state
3. Postgres Client → query customer data and record transactions

Quick Start:
    from audit_service.kafka_producer import publish_event
    from audit_service.event_schemas import FeeWaiverEvent
    from audit_service.redis_client import RedisSessionClient
    from audit_service.postgres_client import PostgresClient
"""

__version__ = "1.0.0"
__author__ = "Audit Pipeline Team"
