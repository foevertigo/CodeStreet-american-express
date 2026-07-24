"""
test_kafka_producer.py — Unit tests for the Kafka producer.

These tests use mocking so they work WITHOUT a running Kafka instance.
For integration tests (real Kafka), use scripts/verify_pipeline.py.

Run: pytest tests/test_kafka_producer.py -v
"""

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from audit_service.event_schemas import (
    FeeWaiverEvent,
    ComplianceDecisionEvent,
    CreditLimitChangeEvent,
    CardReplacementEvent,
    EscalationEvent,
    SystemErrorEvent,
    EventDecision,
    CardReplacementReason,
    EscalationReason,
)
from audit_service.kafka_producer import publish_event, close_producer


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_producer_singleton():
    """Reset the global producer singleton before each test."""
    import audit_service.kafka_producer as kp
    kp._producer = None
    yield
    kp._producer = None


@pytest.fixture
def mock_kafka_producer():
    """Patches KafkaProducer so no real Kafka connection is made."""
    with patch("audit_service.kafka_producer.KafkaProducer") as MockProducer:
        mock_instance = MagicMock()
        # Simulate successful send() → get() returning record metadata
        mock_future = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.topic = "agent-actions"
        mock_metadata.partition = 0
        mock_metadata.offset = 42
        mock_future.get.return_value = mock_metadata
        mock_instance.send.return_value = mock_future
        MockProducer.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Event Schema Tests
# =============================================================================

class TestEventSchemas:
    """Tests that event models serialize correctly and have required fields."""

    def test_fee_waiver_event_auto_generates_id_and_timestamp(self):
        event = FeeWaiverEvent(
            session_id="sess-test-001",
            account_id="a1111111-0000-0000-0000-000000000001",
            fee_type="late_fee",
            amount_requested=35.00,
            decision=EventDecision.APPROVED,
        )
        assert event.event_id is not None
        assert len(event.event_id) == 36  # UUID format
        assert event.event_timestamp is not None
        assert "T" in event.event_timestamp  # ISO format

    def test_fee_waiver_event_correct_topic(self):
        event = FeeWaiverEvent(
            session_id="sess-001",
            fee_type="late_fee",
            amount_requested=35.0,
            decision=EventDecision.DENIED,
        )
        assert event.topic == "agent-actions"

    def test_compliance_decision_event_correct_topic(self):
        event = ComplianceDecisionEvent(
            session_id="sess-001",
            rule_id="RULE_FEE_4.1",
            rule_description="Fee waiver frequency check",
            decision=EventDecision.DENIED,
        )
        assert event.topic == "compliance-decisions"

    def test_escalation_event_correct_topic(self):
        event = EscalationEvent(
            session_id="sess-001",
            reason=EscalationReason.CUSTOMER_REQUESTED,
        )
        assert event.topic == "escalations"

    def test_system_error_event_correct_topic(self):
        event = SystemErrorEvent(
            session_id="sess-001",
            error_type="ConnectionError",
            error_message="Could not connect to banking API",
            service_name="policy-engine",
        )
        assert event.topic == "system-errors"

    def test_card_replacement_event_correct_topic(self):
        event = CardReplacementEvent(
            session_id="sess-001",
            reason=CardReplacementReason.STOLEN,
            old_card_last_four="1234",
            shipping_address="742 Evergreen Terrace, Springfield, IL 62701",
            old_card_cancelled=True,
        )
        assert event.topic == "card-events"

    def test_event_serializes_to_dict(self):
        event = FeeWaiverEvent(
            session_id="sess-001",
            account_id="a111-test",
            fee_type="late_fee",
            amount_requested=35.0,
            decision=EventDecision.APPROVED,
        )
        d = event.model_dump(mode="json")
        assert d["fee_type"] == "late_fee"
        assert d["decision"] == "approved"
        assert d["topic"] == "agent-actions"
        assert "event_id" in d
        assert "event_timestamp" in d

    def test_two_events_have_different_ids(self):
        e1 = SystemErrorEvent(session_id="s1", error_type="E", error_message="m", service_name="svc")
        e2 = SystemErrorEvent(session_id="s2", error_type="E", error_message="m", service_name="svc")
        assert e1.event_id != e2.event_id


# =============================================================================
# Kafka Producer Tests
# =============================================================================

class TestPublishEvent:
    """Tests for the publish_event() function."""

    def test_publish_fee_waiver_event_success(self, mock_kafka_producer):
        event = FeeWaiverEvent(
            session_id="sess-test-kafka",
            account_id="a1111111-0000-0000-0000-000000000001",
            fee_type="late_fee",
            amount_requested=35.0,
            decision=EventDecision.APPROVED,
        )
        result = publish_event(event)

        assert result["success"] is True
        assert result["event_id"] == event.event_id
        assert result["topic"] == "agent-actions"
        assert result["partition"] == 0
        assert result["offset"] == 42

    def test_publish_sends_to_correct_topic(self, mock_kafka_producer):
        event = ComplianceDecisionEvent(
            session_id="sess-compliance",
            rule_id="RULE_4.1",
            rule_description="Test rule",
            decision=EventDecision.DENIED,
            denial_reason="Credit score below threshold",
        )
        publish_event(event)

        # Verify send() was called with the correct topic
        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["topic"] == "compliance-decisions"

    def test_publish_uses_account_id_as_partition_key(self, mock_kafka_producer):
        account_id = "a1111111-0000-0000-0000-000000000001"
        event = FeeWaiverEvent(
            session_id="sess-001",
            account_id=account_id,
            fee_type="late_fee",
            amount_requested=35.0,
            decision=EventDecision.DENIED,
        )
        publish_event(event)

        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["key"] == account_id

    def test_publish_falls_back_to_session_id_when_no_account(self, mock_kafka_producer):
        event = SystemErrorEvent(
            session_id="sess-no-account",
            # No account_id
            error_type="TimeoutError",
            error_message="Banking API timeout",
            service_name="orchestrator",
        )
        publish_event(event)

        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["key"] == "sess-no-account"

    def test_publish_event_value_is_json_serializable(self, mock_kafka_producer):
        event = CreditLimitChangeEvent(
            session_id="sess-cli",
            account_id="a222-test",
            previous_limit=3000.0,
            requested_limit=10000.0,
            decision=EventDecision.DENIED,
            denial_reason="Credit score below 680",
            credit_score_used=620,
        )
        publish_event(event)

        # Get what was passed to send()'s value argument
        call_args = mock_kafka_producer.send.call_args
        sent_value = call_args.kwargs["value"]

        # The value_serializer in the producer does json.dumps → bytes
        # But since we're mocking the producer, we get the raw dict here
        assert isinstance(sent_value, dict)
        assert sent_value["decision"] == "denied"
        assert sent_value["previous_limit"] == 3000.0
