"""
kafka_producer.py — Publishes audit events to Kafka.

This is the PRIMARY interface for all teams to write to the audit pipeline.

Usage:
    from audit_service.kafka_producer import publish_event, get_producer
    from audit_service.event_schemas import FeeWaiverEvent, EventDecision

    # Example: Publish a fee waiver approval
    event = FeeWaiverEvent(
        session_id="sess-xyz-789",
        account_id="a1111111-0000-0000-0000-000000000001",
        fee_type="late_fee",
        amount_requested=35.00,
        amount_approved=35.00,
        decision=EventDecision.APPROVED,
        agent_reasoning="Customer eligible: no waivers in past 12 months.",
        transaction_id="txn-bank-001"
    )
    result = publish_event(event)
    print(result)  # {"success": True, "topic": "agent-actions", "event_id": "..."}
"""

import json
import logging
from typing import Optional

from kafka import KafkaProducer
from kafka.errors import KafkaError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from audit_service.config import get_settings
from audit_service.event_schemas import BaseAuditEvent

logger = logging.getLogger(__name__)

# Module-level singleton producer (created once, reused for all publishes)
_producer: Optional[KafkaProducer] = None


def get_producer() -> KafkaProducer:
    """
    Returns the Kafka producer singleton.
    Creates it on first call. Subsequent calls return the cached instance.

    The producer is thread-safe. In a FastAPI app, create it at startup
    and share it across all requests.

    Returns:
        KafkaProducer: Configured Kafka producer instance.

    Raises:
        RuntimeError: If Kafka is not reachable.
    """
    global _producer
    if _producer is None:
        settings = get_settings()
        logger.info(
            "Initializing Kafka producer",
            extra={"bootstrap_servers": settings.kafka_bootstrap_servers}
        )
        try:
            _producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                # Serialize Python dict → JSON bytes
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # Use event_id as the partition key → same account events to same partition
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                # Durability settings
                acks=settings.kafka_producer_ack,       # Wait for all replicas
                retries=settings.kafka_producer_retries,
                retry_backoff_ms=200,
                # Performance settings
                linger_ms=10,            # Wait up to 10ms to batch messages
                batch_size=16384,        # 16KB batch
                compression_type="gzip",
                # Reliability
                request_timeout_ms=30000,
                max_block_ms=10000,      # Max time to wait if buffer is full
            )
            logger.info("Kafka producer initialized successfully")
        except KafkaError as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise RuntimeError(f"Kafka connection failed: {e}") from e

    return _producer


def close_producer() -> None:
    """
    Gracefully closes the Kafka producer and flushes pending messages.
    Call this on application shutdown (FastAPI lifespan, atexit, etc.)

    Example (FastAPI):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield
            close_producer()  # <-- add this
    """
    global _producer
    if _producer is not None:
        logger.info("Flushing and closing Kafka producer...")
        _producer.flush(timeout=10)
        _producer.close()
        _producer = None
        logger.info("Kafka producer closed.")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(KafkaError),
    reraise=True,
)
def publish_event(event: BaseAuditEvent) -> dict:
    """
    Publishes an audit event to the appropriate Kafka topic.

    The topic is determined by event.topic (set automatically by each event class).
    The partition key is event.account_id (ensures ordering per customer).

    Args:
        event: Any event model from audit_service.event_schemas

    Returns:
        dict with keys: success (bool), topic (str), event_id (str),
                        partition (int), offset (int)

    Raises:
        KafkaError: If publish fails after 3 retries (with exponential backoff).

    Example:
        result = publish_event(my_event)
        # {"success": True, "topic": "agent-actions", "event_id": "uuid-...",
        #  "partition": 0, "offset": 42}
    """
    producer = get_producer()

    # Serialize event to dict (Pydantic handles nested models, enums, datetimes)
    event_dict = event.model_dump(mode="json")
    topic = event.topic

    # Use account_id as partition key for ordering guarantees per customer.
    # If no account_id (e.g. pre-auth error), use session_id.
    partition_key = event.account_id or event.session_id

    try:
        future = producer.send(
            topic=topic,
            value=event_dict,
            key=partition_key,
        )
        # Block until the message is acknowledged (or timeout)
        record_metadata = future.get(timeout=10)

        result = {
            "success": True,
            "topic": record_metadata.topic,
            "event_id": event.event_id,
            "partition": record_metadata.partition,
            "offset": record_metadata.offset,
        }
        logger.info(
            "Audit event published",
            extra={
                "topic": topic,
                "event_id": event.event_id,
                "event_type": event_dict.get("event_type"),
                "account_id": event.account_id,
                "partition": record_metadata.partition,
                "offset": record_metadata.offset,
            }
        )
        return result

    except KafkaError as e:
        logger.error(
            "Failed to publish audit event",
            extra={
                "topic": topic,
                "event_id": event.event_id,
                "error": str(e),
            }
        )
        raise


def publish_event_fire_and_forget(event: BaseAuditEvent) -> str:
    """
    Publishes an event without waiting for acknowledgement.
    Use this for non-critical logging where speed > reliability.
    Returns the event_id immediately.

    For critical financial events (fee waivers, limit changes), use publish_event() instead.
    """
    producer = get_producer()
    event_dict = event.model_dump(mode="json")
    partition_key = event.account_id or event.session_id

    producer.send(topic=event.topic, value=event_dict, key=partition_key)
    logger.debug(f"Fire-and-forget publish: event_id={event.event_id} topic={event.topic}")
    return event.event_id
