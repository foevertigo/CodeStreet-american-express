"""
event_schemas.py — Pydantic models for all Kafka audit events.

IMPORTANT FOR ALL TEAMS:
    Every event published to Kafka MUST be one of these models.
    This ensures:
      - Type safety at publish time
      - Consistent JSON structure in Elasticsearch
      - Every event has an event_id for idempotent Logstash writes

Usage:
    from audit_service.event_schemas import FeeWaiverEvent, EventDecision
    from audit_service.kafka_producer import publish_event

    event = FeeWaiverEvent(
        session_id="sess-abc123",
        account_id="a1111111-0000-0000-0000-000000000001",
        fee_type="late_fee",
        amount=35.00,
        decision=EventDecision.APPROVED,
        policy_version="v1.0",
        agent_reasoning="Customer in good standing, first waiver in 12 months."
    )
    publish_event(event)
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Enums — shared constants used across all event types
# =============================================================================

class EventDecision(str, Enum):
    """Outcome of a compliance/policy check."""
    APPROVED         = "approved"
    DENIED           = "denied"
    PENDING_REVIEW   = "pending_review"
    ESCALATED        = "escalated"


class EventSeverity(str, Enum):
    """Alert severity for Kibana dashboards."""
    INFO     = "info"
    WARNING  = "warning"
    HIGH     = "high"
    CRITICAL = "critical"


class CardReplacementReason(str, Enum):
    DAMAGED  = "damaged"
    LOST     = "lost"
    STOLEN   = "stolen"
    EXPIRED  = "expired"
    FRAUD    = "fraud"


class EscalationReason(str, Enum):
    POLICY_DENIED       = "policy_denied"
    CUSTOMER_REQUESTED  = "customer_requested"
    SYSTEM_ERROR        = "system_error"
    FRAUD_DETECTED      = "fraud_detected"
    COMPLEX_QUERY       = "complex_query"


# =============================================================================
# Base Event — all events inherit from this
# =============================================================================

class BaseAuditEvent(BaseModel):
    """
    Base class for all audit events.
    Every event automatically gets:
      - event_id: UUID for idempotent Elasticsearch writes
      - event_timestamp: ISO 8601 timestamp in UTC
      - topic: Kafka topic this event should be sent to (set by subclass)
    """
    event_id:         str       = Field(default_factory=lambda: str(uuid.uuid4()))
    event_timestamp:  str       = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    session_id:       str       = Field(..., description="LangGraph session ID (Redis key)")
    account_id:       Optional[str] = Field(None, description="Customer account UUID")
    channel:          str       = Field(default="web", description="web | voice | mobile")
    agent_reasoning:  Optional[str] = Field(None, description="LLM explanation for this action")
    policy_version:   str       = Field(default="v1.0", description="Policy engine version used")
    severity:         EventSeverity = Field(default=EventSeverity.INFO)

    # Subclasses MUST set this — it determines which Kafka topic to publish to
    topic: str = Field(default="agent-actions", exclude=False)

    model_config = {"use_enum_values": True}


# =============================================================================
# Event Types — one per business action
# =============================================================================

class FeeWaiverEvent(BaseAuditEvent):
    """
    Published when the AI agent processes a fee waiver request.
    Topic: agent-actions (action) + compliance-decisions (decision)

    Publish ONE of these after calling check_fee_waiver_eligibility().
    """
    topic:            str           = "agent-actions"
    event_type:       str           = "FEE_WAIVER_EVALUATED"

    fee_type:         str           = Field(..., description="late_fee | annual_fee | overdraft_fee")
    amount_requested: float         = Field(..., description="Dollar amount the customer wants waived")
    amount_approved:  float         = Field(default=0.0, description="Actual amount waived (0 if denied)")
    decision:         EventDecision = Field(..., description="approved | denied")
    denial_reason:    Optional[str] = Field(None, description="Required if decision=denied")
    transaction_id:   Optional[str] = Field(None, description="Bank transaction ID if approved")
    waivers_this_year: int          = Field(default=0, description="Number of waivers in last 12 months")


class ComplianceDecisionEvent(BaseAuditEvent):
    """
    Published by the Policy Engine after ANY compliance check.
    Topic: compliance-decisions

    Policy Engine team: Publish this for EVERY eligibility check.
    This is the primary compliance audit trail.
    """
    topic:            str           = "compliance-decisions"
    event_type:       str           = "COMPLIANCE_DECISION"
    severity:         EventSeverity = EventSeverity.WARNING  # Default WARNING for compliance events

    rule_id:          str           = Field(..., description="e.g., 'RULE_FEE_WAIVER_FREQUENCY_4.1'")
    rule_description: str           = Field(..., description="Human-readable rule description")
    decision:         EventDecision = Field(..., description="approved | denied | escalated")
    denial_reason:    Optional[str] = Field(None)
    input_data:       dict[str, Any] = Field(default_factory=dict, description="Data the rule evaluated")
    output_data:      dict[str, Any] = Field(default_factory=dict, description="Rule engine output")


class CreditLimitChangeEvent(BaseAuditEvent):
    """
    Published when the AI agent processes a credit limit increase request.
    Topic: agent-actions
    """
    topic:              str           = "agent-actions"
    event_type:         str           = "CREDIT_LIMIT_CHANGE_EVALUATED"

    previous_limit:     float         = Field(..., description="Current credit limit before change")
    requested_limit:    float         = Field(..., description="Limit the customer requested")
    approved_limit:     Optional[float] = Field(None, description="Actual new limit (None if denied)")
    decision:           EventDecision = Field(...)
    denial_reason:      Optional[str] = Field(None)
    credit_score_used:  Optional[int] = Field(None, description="Credit score at time of decision")
    income_reported:    Optional[float] = Field(None, description="Customer-stated income")


class CardReplacementEvent(BaseAuditEvent):
    """
    Published when the AI agent initiates a card replacement.
    Topic: card-events

    IMPORTANT: If reason is LOST or STOLEN, old card should be cancelled BEFORE publishing.
    """
    topic:              str                  = "card-events"
    event_type:         str                  = "CARD_REPLACEMENT_INITIATED"
    severity:           EventSeverity        = EventSeverity.WARNING

    reason:             CardReplacementReason = Field(...)
    old_card_last_four: str                  = Field(..., description="Last 4 digits of old card")
    new_card_last_four: Optional[str]        = Field(None, description="Last 4 of new card (set when issued)")
    old_card_cancelled: bool                 = Field(default=False, description="True if old number was cancelled")
    shipping_address:   str                  = Field(..., description="Confirmed delivery address")
    expedited:          bool                 = Field(default=False)
    replacement_id:     Optional[str]        = Field(None, description="DB record ID")


class EscalationEvent(BaseAuditEvent):
    """
    Published when the AI agent cannot resolve a request and hands off to a human.
    Topic: escalations

    This triggers the Human Support Dashboard alert.
    """
    topic:          str              = "escalations"
    event_type:     str              = "HUMAN_ESCALATION_TRIGGERED"
    severity:       EventSeverity    = EventSeverity.HIGH

    reason:         EscalationReason = Field(...)
    original_intent: Optional[str]   = Field(None, description="What the customer was trying to do")
    conversation_turns: int          = Field(default=0, description="Number of turns before escalation")
    context_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of relevant state for the human agent"
    )


class SystemErrorEvent(BaseAuditEvent):
    """
    Published when an unhandled exception or critical failure occurs.
    Topic: system-errors

    All teams should publish this when catching unexpected exceptions.
    """
    topic:          str           = "system-errors"
    event_type:     str           = "SYSTEM_ERROR"
    severity:       EventSeverity = EventSeverity.CRITICAL

    error_type:     str           = Field(..., description="Exception class name")
    error_message:  str           = Field(..., description="Exception message")
    stack_trace:    Optional[str] = Field(None)
    service_name:   str           = Field(..., description="Which microservice threw this, e.g. 'policy-engine'")
    recovery_action: Optional[str] = Field(None, description="What the system did to recover")


class TravelNotificationEvent(BaseAuditEvent):
    """
    Published when a customer sets up a travel notification.
    Topic: agent-actions
    """
    topic:            str           = "agent-actions"
    event_type:       str           = "TRAVEL_NOTIFICATION_SET"

    destination:      str           = Field(..., description="Country or city")
    travel_start_date: str          = Field(..., description="YYYY-MM-DD")
    travel_end_date:  str           = Field(..., description="YYYY-MM-DD")
    fraud_rule_id:    Optional[str] = Field(None, description="ID of rule created in fraud system")


# =============================================================================
# Union type — for type hints when you want to accept any event
# =============================================================================
AuditEvent = (
    FeeWaiverEvent |
    ComplianceDecisionEvent |
    CreditLimitChangeEvent |
    CardReplacementEvent |
    EscalationEvent |
    SystemErrorEvent |
    TravelNotificationEvent
)
