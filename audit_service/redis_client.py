"""
redis_client.py — LangGraph Conversation State Manager.

Provides a simple CRUD interface over Redis for storing/retrieving
LangGraph conversation state (session memory).

SESSION STRUCTURE:
    Key:   session:{session_id}
    Value: JSON blob (the full LangGraph state dict)
    TTL:   30 minutes (reset on every update = sliding expiry)

Usage (for LangGraph Orchestrator):
    from audit_service.redis_client import RedisSessionClient

    client = RedisSessionClient()

    # Save session state after each LangGraph turn
    client.set_session("sess-abc123", {
        "messages": [...],
        "authenticated_user_id": "a1111111-...",
        "intent": "fee_waiver",
        "collected_entities": {"fee_type": "late_fee"}
    })

    # Load session at start of each turn
    state = client.get_session("sess-abc123")
    if state is None:
        # Session expired or doesn't exist — start fresh
        ...

    # Delete on session end / escalation
    client.delete_session("sess-abc123")
"""

import json
import logging
from typing import Any, Optional

import redis
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from audit_service.config import get_settings

logger = logging.getLogger(__name__)

# Module-level Redis client singleton
_redis_client: Optional[redis.Redis] = None

SESSION_KEY_PREFIX = "session:"
AGENT_LOCK_PREFIX  = "lock:"


def get_redis_client() -> redis.Redis:
    """
    Returns the Redis client singleton.
    Creates it on first call (lazy initialization).

    Returns:
        redis.Redis: Connected Redis client.

    Raises:
        redis.ConnectionError: If Redis is not reachable.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        logger.info(f"Connecting to Redis: {settings.redis_url}")
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,   # Return str, not bytes
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Ping to verify connection
        _redis_client.ping()
        logger.info("Redis client connected successfully")
    return _redis_client


class RedisSessionClient:
    """
    High-level interface for managing LangGraph session state in Redis.

    Example:
        client = RedisSessionClient()
        client.set_session("my-session", {"intent": "fee_waiver"})
        state = client.get_session("my-session")
    """

    def __init__(self):
        self.client = get_redis_client()
        self.settings = get_settings()
        self.ttl = self.settings.redis_session_ttl_seconds

    def _make_key(self, session_id: str) -> str:
        """Builds the Redis key for a session. Internal use."""
        return f"{SESSION_KEY_PREFIX}{session_id}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_type(redis.RedisError),
        reraise=True,
    )
    def set_session(self, session_id: str, state: dict[str, Any]) -> bool:
        """
        Saves (or updates) conversation state for a session.
        Automatically resets the 30-minute TTL (sliding expiry).

        Args:
            session_id: Unique session identifier (e.g., UUID or Twilio CallSID)
            state:      Full LangGraph state dict

        Returns:
            True if saved successfully.

        Example:
            client.set_session("sess-xyz", {
                "messages": [...],
                "authenticated_user_id": "a111...",
                "intent": "fee_waiver",
                "collected_entities": {"fee_type": "late_fee", "amount": 35.0},
                "eligibility_status": None,
                "requires_escalation": False
            })
        """
        key = self._make_key(session_id)
        serialized = json.dumps(state, default=str)  # default=str handles datetime, UUID etc.
        result = self.client.setex(
            name=key,
            time=self.ttl,    # Sliding TTL — resets on every update
            value=serialized,
        )
        logger.debug(f"Session saved: {session_id} (TTL: {self.ttl}s)")
        return bool(result)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_type(redis.RedisError),
        reraise=True,
    )
    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieves conversation state for a session.

        Args:
            session_id: Session identifier.

        Returns:
            State dict if session exists and is not expired.
            None if session not found or expired.

        Example:
            state = client.get_session("sess-xyz")
            if state is None:
                # Session expired — re-authenticate user
                return redirect_to_auth()
            current_intent = state.get("intent")
        """
        key = self._make_key(session_id)
        raw = self.client.get(key)
        if raw is None:
            logger.debug(f"Session not found or expired: {session_id}")
            return None
        return json.loads(raw)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_type(redis.RedisError),
        reraise=True,
    )
    def delete_session(self, session_id: str) -> bool:
        """
        Deletes a session (call on logout, escalation, or session end).

        Returns True if the key existed and was deleted, False if it didn't exist.
        """
        key = self._make_key(session_id)
        deleted = self.client.delete(key)
        logger.info(f"Session deleted: {session_id}")
        return bool(deleted)

    def session_exists(self, session_id: str) -> bool:
        """
        Checks if a session exists without fetching its full content.
        More efficient than get_session() when you only need existence check.
        """
        key = self._make_key(session_id)
        return bool(self.client.exists(key))

    def get_session_ttl(self, session_id: str) -> int:
        """
        Returns remaining TTL in seconds for a session.
        Returns -1 if key has no TTL, -2 if key doesn't exist.
        """
        key = self._make_key(session_id)
        return self.client.ttl(key)

    def update_session_field(self, session_id: str, field: str, value: Any) -> bool:
        """
        Updates a single field in the session state without loading the full state.
        Useful for quick status updates (e.g., setting eligibility_status after policy check).

        Args:
            session_id: Session identifier
            field:      The key to update in the state dict
            value:      New value for that key

        Example:
            client.update_session_field("sess-xyz", "eligibility_status", "approved")
            client.update_session_field("sess-xyz", "requires_escalation", True)
        """
        state = self.get_session(session_id)
        if state is None:
            logger.warning(f"Cannot update field '{field}': session {session_id} not found")
            return False
        state[field] = value
        return self.set_session(session_id, state)

    def health_check(self) -> bool:
        """
        Pings Redis to verify connectivity.
        Returns True if healthy.
        """
        try:
            return self.client.ping()
        except redis.RedisError as e:
            logger.error(f"Redis health check failed: {e}")
            return False
