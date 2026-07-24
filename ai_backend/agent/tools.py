"""
tools.py — Deterministic Policy Engine & Banking Microservices Tools (Optimized with Fast DB Health Checks)
"""

import logging
from typing import Optional, Dict, Any
from langchain_core.tools import tool

from audit_service.postgres_client import PostgresClient
from audit_service.kafka_producer import publish_event
from audit_service.event_schemas import (
    FeeWaiverEvent,
    ComplianceDecisionEvent,
    CreditLimitChangeEvent,
    CardReplacementEvent,
    EscalationEvent,
    TravelNotificationEvent,
    EventDecision,
    EventSeverity,
    CardReplacementReason,
    EscalationReason,
)
from ai_backend.auth import get_customer_profile

logger = logging.getLogger(__name__)

# Global reference to websocket supervisor broadcast callback if initialized
_supervisor_broadcast_func = None
_db_healthy: Optional[bool] = None

def set_supervisor_broadcaster(func):
    global _supervisor_broadcast_func
    _supervisor_broadcast_func = func


def is_db_available() -> bool:
    global _db_healthy
    if _db_healthy is None:
        try:
            client = PostgresClient()
            _db_healthy = client.health_check()
        except Exception:
            _db_healthy = False
    return _db_healthy


def safe_publish_event(event):
    """Safely attempts to publish Kafka audit event."""
    try:
        publish_event(event)
    except Exception as e:
        logger.warning(f"Kafka event publish skipped (bus offline/connecting): {e}")


@tool
def tool_waive_fee(account_id: str, fee_type: str = "late_fee", amount_requested: float = 35.0, session_id: str = "session-default") -> str:
    """
    Evaluates fee waiver eligibility against compliance rules and updates database.
    Rule: Denied if customer had an approved fee waiver in the last 12 months.
    """
    logger.info(f"Executing tool_waive_fee: account={account_id}, fee_type={fee_type}, amount={amount_requested}")
    customer = get_customer_profile(account_id)
    if not customer:
        return f"Error: Customer profile not found for account_id {account_id}."
    
    waivers_last_year = customer.get("waivers_last_year", 0)
    if is_db_available():
        try:
            client = PostgresClient()
            waivers_last_year = client.get_fee_waiver_count_last_year(account_id)
        except Exception as e:
            logger.warning(f"DB fee waiver count query fallback: {e}")
    
    # Apply Compliance Policy Rule
    if waivers_last_year >= 1:
        # DENIED
        denial_reason = "Customer has already received an approved fee waiver within the past 12 months (Policy RULE_FEE_WAIVER_FREQUENCY_12M)."
        
        if is_db_available():
            try:
                client = PostgresClient()
                client.record_fee_waiver(
                    account_id=account_id,
                    fee_type=fee_type,
                    amount_requested=amount_requested,
                    amount_approved=0.0,
                    decision="denied",
                    session_id=session_id,
                    denial_reason=denial_reason
                )
            except Exception as e:
                logger.warning(f"DB record fee waiver error: {e}")
        
        comp_event = ComplianceDecisionEvent(
            session_id=session_id,
            account_id=account_id,
            rule_id="RULE_FEE_WAIVER_FREQUENCY_12M",
            rule_description="Maximum 1 fee waiver per 12-month period",
            decision=EventDecision.DENIED,
            denial_reason=denial_reason,
            input_data={"waivers_in_past_year": waivers_last_year, "fee_type": fee_type, "amount": amount_requested},
            output_data={"approved": False}
        )
        safe_publish_event(comp_event)
            
        action_event = FeeWaiverEvent(
            session_id=session_id,
            account_id=account_id,
            fee_type=fee_type,
            amount_requested=amount_requested,
            amount_approved=0.0,
            decision=EventDecision.DENIED,
            denial_reason=denial_reason,
            waivers_this_year=waivers_last_year,
            agent_reasoning=denial_reason
        )
        safe_publish_event(action_event)

        return (
            f"FEE WAIVER DENIED: Card member {customer.get('first_name')} {customer.get('last_name')} "
            f"has already received an approved fee waiver in the past 12 months. "
            f"According to AmEx policy RULE_FEE_WAIVER_FREQUENCY_12M, only 1 waiver is permitted per year."
        )

    else:
        # APPROVED
        waiver_id = "WVR-" + account_id[:8].upper()
        if is_db_available():
            try:
                client = PostgresClient()
                waiver_id = client.record_fee_waiver(
                    account_id=account_id,
                    fee_type=fee_type,
                    amount_requested=amount_requested,
                    amount_approved=amount_requested,
                    decision="approved",
                    session_id=session_id,
                    transaction_id="TXN-CREDIT-WAIVER-001"
                )
            except Exception as e:
                logger.warning(f"DB record fee waiver error: {e}")
        
        comp_event = ComplianceDecisionEvent(
            session_id=session_id,
            account_id=account_id,
            rule_id="RULE_FEE_WAIVER_FREQUENCY_12M",
            rule_description="Maximum 1 fee waiver per 12-month period",
            decision=EventDecision.APPROVED,
            input_data={"waivers_in_past_year": 0, "fee_type": fee_type, "amount": amount_requested},
            output_data={"approved": True, "amount_approved": amount_requested, "waiver_id": waiver_id}
        )
        safe_publish_event(comp_event)

        action_event = FeeWaiverEvent(
            session_id=session_id,
            account_id=account_id,
            fee_type=fee_type,
            amount_requested=amount_requested,
            amount_approved=amount_requested,
            decision=EventDecision.APPROVED,
            transaction_id="TXN-CREDIT-WAIVER-001",
            waivers_this_year=0,
            agent_reasoning="Customer eligible: 0 fee waivers in past 12 months."
        )
        safe_publish_event(action_event)

        return (
            f"FEE WAIVER APPROVED: ${amount_requested:.2f} {fee_type.replace('_', ' ')} waiver successfully processed "
            f"for {customer.get('first_name')} {customer.get('last_name')}. Credit reference ID: TXN-CREDIT-WAIVER-001."
        )


@tool
def tool_increase_limit(account_id: str, requested_amount: float, income: float, session_id: str = "session-default") -> str:
    """
    Evaluates credit limit increase request against risk models and updates customer account.
    Rule: Credit score must be > 700 and requested limit <= (income * 0.20).
    """
    logger.info(f"Executing tool_increase_limit: account={account_id}, limit={requested_amount}, income={income}")
    customer = get_customer_profile(account_id)
    if not customer:
        return f"Error: Customer account_id {account_id} not found."
    
    current_limit = float(customer.get("credit_limit", 0.0))
    credit_score = int(customer.get("credit_score", 0))
    max_allowed = income * 0.20

    score_ok = credit_score > 700
    limit_ok = requested_amount <= max_allowed

    if score_ok and limit_ok:
        # APPROVE
        if is_db_available():
            try:
                client = PostgresClient()
                client.record_credit_limit_change(
                    account_id=account_id,
                    previous_limit=current_limit,
                    requested_limit=requested_amount,
                    approved_limit=requested_amount,
                    decision="approved",
                    session_id=session_id,
                    credit_score=credit_score,
                    income_reported=income
                )
            except Exception as e:
                logger.warning(f"DB record limit change error: {e}")

        comp_event = ComplianceDecisionEvent(
            session_id=session_id,
            account_id=account_id,
            rule_id="RULE_CREDIT_LIMIT_MULTIPLICATIVE_RISK",
            rule_description="Credit Score > 700 AND requested_limit <= 20% of annual income",
            decision=EventDecision.APPROVED,
            input_data={"credit_score": credit_score, "income": income, "requested_limit": requested_amount},
            output_data={"approved_limit": requested_amount}
        )
        safe_publish_event(comp_event)

        action_event = CreditLimitChangeEvent(
            session_id=session_id,
            account_id=account_id,
            previous_limit=current_limit,
            requested_limit=requested_amount,
            approved_limit=requested_amount,
            decision=EventDecision.APPROVED,
            credit_score_used=credit_score,
            income_reported=income,
            agent_reasoning=f"Approved: Credit score {credit_score} > 700 and requested limit ${requested_amount:,.2f} <= 20% of income (${max_allowed:,.2f})."
        )
        safe_publish_event(action_event)

        return (
            f"CREDIT LIMIT INCREASE APPROVED! The credit limit for {customer.get('first_name')} {customer.get('last_name')} "
            f"has been increased from ${current_limit:,.2f} to ${requested_amount:,.2f}. Effective immediately."
        )
    else:
        # DENIED
        reasons = []
        if not score_ok:
            reasons.append(f"Credit score ({credit_score}) is below the required 701 minimum threshold.")
        if not limit_ok:
            reasons.append(f"Requested limit (${requested_amount:,.2f}) exceeds maximum allowed cap of 20% of income (${max_allowed:,.2f}).")
        
        denial_reason = " ".join(reasons)

        if is_db_available():
            try:
                client = PostgresClient()
                client.record_credit_limit_change(
                    account_id=account_id,
                    previous_limit=current_limit,
                    requested_limit=requested_amount,
                    approved_limit=None,
                    decision="denied",
                    session_id=session_id,
                    denial_reason=denial_reason,
                    credit_score=credit_score,
                    income_reported=income
                )
            except Exception as e:
                logger.warning(f"DB record limit change error: {e}")

        comp_event = ComplianceDecisionEvent(
            session_id=session_id,
            account_id=account_id,
            rule_id="RULE_CREDIT_LIMIT_MULTIPLICATIVE_RISK",
            rule_description="Credit Score > 700 AND requested_limit <= 20% of annual income",
            decision=EventDecision.DENIED,
            denial_reason=denial_reason,
            input_data={"credit_score": credit_score, "income": income, "requested_limit": requested_amount},
            output_data={"approved": False}
        )
        safe_publish_event(comp_event)

        action_event = CreditLimitChangeEvent(
            session_id=session_id,
            account_id=account_id,
            previous_limit=current_limit,
            requested_limit=requested_amount,
            approved_limit=None,
            decision=EventDecision.DENIED,
            denial_reason=denial_reason,
            credit_score_used=credit_score,
            income_reported=income,
            agent_reasoning=denial_reason
        )
        safe_publish_event(action_event)

        return (
            f"CREDIT LIMIT INCREASE DENIED: {denial_reason} "
            f"Current credit limit remains ${current_limit:,.2f}."
        )


@tool
def tool_replace_card(account_id: str, reason: str, shipping_address: str, expedited: bool = False, session_id: str = "session-default") -> str:
    """
    Orders a replacement card. If reason is 'lost', 'stolen', or 'fraud', automatically freezes/cancels old card immediately.
    """
    logger.info(f"Executing tool_replace_card: account={account_id}, reason={reason}, address={shipping_address}")
    customer = get_customer_profile(account_id)
    if not customer:
        return f"Error: Customer profile not found for account {account_id}."
    
    clean_reason = reason.lower().strip()
    if clean_reason not in ["damaged", "lost", "stolen", "expired", "fraud"]:
        clean_reason = "lost" if "lost" in clean_reason or "stolen" in clean_reason else "damaged"

    old_card_last_four = "8899"
    card_cancelled = clean_reason in ["lost", "stolen", "fraud"]
    replacement_id = "CRD-REP-" + account_id[:8].upper()

    if is_db_available():
        try:
            client = PostgresClient()
            replacement_id = client.record_card_replacement(
                account_id=account_id,
                reason=clean_reason,
                old_card_last_four=old_card_last_four,
                shipping_address=shipping_address,
                session_id=session_id,
                expedited=expedited
            )
        except Exception as e:
            logger.warning(f"DB record card replacement error: {e}")

    enum_reason = CardReplacementReason.LOST
    try:
        enum_reason = CardReplacementReason(clean_reason)
    except ValueError:
        pass

    event = CardReplacementEvent(
        session_id=session_id,
        account_id=account_id,
        reason=enum_reason,
        old_card_last_four=old_card_last_four,
        old_card_cancelled=card_cancelled,
        shipping_address=shipping_address,
        expedited=expedited,
        replacement_id=replacement_id,
        severity=EventSeverity.HIGH if card_cancelled else EventSeverity.INFO,
        agent_reasoning=f"Replacement card ordered due to {clean_reason}. Old card status: {'CANCELLED/FROZEN' if card_cancelled else 'ACTIVE'}."
    )
    safe_publish_event(event)

    freeze_notice = " [SECURITY ACTION: Old card ending in ****8899 has been IMMEDIATELY FROZEN & CANCELLED to prevent unauthorized charges.]" if card_cancelled else ""
    delivery_speed = "1-2 business days (Expedited Shipping)" if expedited else "3-5 business days (Standard Shipping)"

    return (
        f"CARD REPLACEMENT CONFIRMED for {customer.get('first_name')} {customer.get('last_name')}.{freeze_notice} "
        f"A new card is being dispatched to {shipping_address} via {delivery_speed}. Replacement ID: {replacement_id}."
    )


@tool
def tool_set_travel_notification(account_id: str, destination: str, start_date: str, end_date: str, session_id: str = "session-default") -> str:
    """
    Registers a travel plan to prevent false positive fraud blocks while traveling.
    """
    logger.info(f"Executing tool_set_travel_notification: account={account_id}, dest={destination}, dates={start_date} to {end_date}")
    customer = get_customer_profile(account_id)
    name = customer.get("first_name", "Card Member") if customer else "Card Member"

    event = TravelNotificationEvent(
        session_id=session_id,
        account_id=account_id,
        destination=destination,
        travel_start_date=start_date,
        travel_end_date=end_date,
        fraud_rule_id="FRAUD-RULE-TRAVEL-PASSTHRU-009",
        agent_reasoning=f"Travel alert set for {destination} from {start_date} to {end_date}."
    )
    safe_publish_event(event)

    return (
        f"TRAVEL NOTIFICATION SET: AmEx cards for {name} are now configured for travel to {destination} "
        f"from {start_date} to {end_date}. Your transactions will be authorized seamlessly without fraud holds."
    )


@tool
def tool_escalate_to_human(account_id: str, reason: str, summary: str, session_id: str = "session-default") -> str:
    """
    Escalates conversation to a live human supervisor dashboard with complete context.
    """
    logger.info(f"Executing tool_escalate_to_human: account={account_id}, reason={reason}")
    customer = get_customer_profile(account_id)
    cust_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}" if customer else account_id

    if is_db_available():
        try:
            client = PostgresClient()
            client.end_agent_session(
                session_id=session_id,
                outcome="escalated",
                intent_detected="human_escalation",
                escalated=True
            )
        except Exception as e:
            logger.warning(f"Postgres session end update warning: {e}")

    event = EscalationEvent(
        session_id=session_id,
        account_id=account_id,
        reason=EscalationReason.CUSTOMER_REQUESTED if "request" in reason.lower() else EscalationReason.POLICY_DENIED,
        original_intent=reason,
        context_snapshot={"summary": summary, "customer_name": cust_name, "account_id": account_id},
        severity=EventSeverity.HIGH,
        agent_reasoning=f"Human escalation triggered: {reason}. Summary: {summary}"
    )
    safe_publish_event(event)

    global _supervisor_broadcast_func
    if _supervisor_broadcast_func:
        try:
            _supervisor_broadcast_func({
                "type": "ESCALATION_ALERT",
                "session_id": session_id,
                "account_id": account_id,
                "customer_name": cust_name,
                "reason": reason,
                "summary": summary,
                "timestamp": event.event_timestamp
            })
        except Exception as e:
            logger.warning(f"Supervisor broadcast error: {e}")

    return (
        f"HUMAN ESCALATION TRIGGERED: Session {session_id} for {cust_name} has been transferred to the Supervisor Escalation Queue. "
        f"A human agent is reviewing the context summary: '{summary}' and will take over the chat immediately."
    )
