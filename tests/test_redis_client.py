"""
test_redis_client.py — Unit tests for the Redis session client.

Uses mocking so tests run without a real Redis instance.

Run: pytest tests/test_redis_client.py -v
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from audit_service.redis_client import RedisSessionClient


@pytest.fixture
def mock_redis():
    """Patches redis.from_url so no real Redis connection is made."""
    with patch("audit_service.redis_client.redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client
        yield mock_client


@pytest.fixture(autouse=True)
def reset_redis_singleton():
    """Reset the global Redis singleton before each test."""
    import audit_service.redis_client as rc
    rc._redis_client = None
    yield
    rc._redis_client = None


@pytest.fixture
def session_client(mock_redis):
    return RedisSessionClient()


class TestRedisSessionClient:

    def test_set_session_calls_setex_with_correct_key(self, session_client, mock_redis):
        mock_redis.setex.return_value = True

        state = {"intent": "fee_waiver", "messages": []}
        result = session_client.set_session("sess-abc123", state)

        assert result is True
        call_args = mock_redis.setex.call_args
        assert call_args.kwargs["name"] == "session:sess-abc123"
        assert call_args.kwargs["time"] == session_client.ttl

    def test_set_session_serializes_state_to_json(self, session_client, mock_redis):
        mock_redis.setex.return_value = True
        state = {"intent": "fee_waiver", "amount": 35.0, "decision": None}

        session_client.set_session("sess-abc123", state)

        call_args = mock_redis.setex.call_args
        stored_value = call_args.kwargs["value"]
        # Verify it's valid JSON
        parsed = json.loads(stored_value)
        assert parsed["intent"] == "fee_waiver"
        assert parsed["amount"] == 35.0

    def test_get_session_returns_dict_when_found(self, session_client, mock_redis):
        state = {"intent": "limit_increase", "authenticated_user_id": "a111"}
        mock_redis.get.return_value = json.dumps(state)

        result = session_client.get_session("sess-abc123")

        assert result is not None
        assert result["intent"] == "limit_increase"
        mock_redis.get.assert_called_once_with("session:sess-abc123")

    def test_get_session_returns_none_when_expired(self, session_client, mock_redis):
        mock_redis.get.return_value = None

        result = session_client.get_session("sess-expired")

        assert result is None

    def test_delete_session_returns_true_when_deleted(self, session_client, mock_redis):
        mock_redis.delete.return_value = 1  # Redis returns 1 for successful delete

        result = session_client.delete_session("sess-abc123")

        assert result is True
        mock_redis.delete.assert_called_once_with("session:sess-abc123")

    def test_delete_session_returns_false_when_not_found(self, session_client, mock_redis):
        mock_redis.delete.return_value = 0  # Redis returns 0 if key didn't exist

        result = session_client.delete_session("sess-nonexistent")

        assert result is False

    def test_session_exists_true(self, session_client, mock_redis):
        mock_redis.exists.return_value = 1

        assert session_client.session_exists("sess-abc123") is True
        mock_redis.exists.assert_called_once_with("session:sess-abc123")

    def test_session_exists_false(self, session_client, mock_redis):
        mock_redis.exists.return_value = 0

        assert session_client.session_exists("sess-gone") is False

    def test_update_session_field_updates_single_field(self, session_client, mock_redis):
        # Simulate get → modify → set cycle
        original_state = {
            "intent": "fee_waiver",
            "eligibility_status": None,
            "requires_escalation": False
        }
        mock_redis.get.return_value = json.dumps(original_state)
        mock_redis.setex.return_value = True

        result = session_client.update_session_field("sess-abc", "eligibility_status", "approved")

        assert result is True
        # Verify the setex was called with updated state
        call_args = mock_redis.setex.call_args
        updated_state = json.loads(call_args.kwargs["value"])
        assert updated_state["eligibility_status"] == "approved"
        assert updated_state["intent"] == "fee_waiver"  # Other fields preserved

    def test_update_session_field_returns_false_when_session_not_found(self, session_client, mock_redis):
        mock_redis.get.return_value = None  # Session expired

        result = session_client.update_session_field("sess-gone", "intent", "new_value")

        assert result is False

    def test_health_check_returns_true_on_ping(self, session_client, mock_redis):
        mock_redis.ping.return_value = True
        assert session_client.health_check() is True

    def test_session_key_prefix_is_applied(self, session_client):
        assert session_client._make_key("my-session") == "session:my-session"
