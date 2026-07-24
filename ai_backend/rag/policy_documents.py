"""
policy_documents.py — Authoritative compliance rule text (single source of truth).
The RAG engine ingests these at startup. The LLM only quotes from these chunks —
zero hallucinated policy content.
"""

COMPLIANCE_RULES = [
    {
        "id": "RULE_FEE_WAIVER_FREQUENCY_12M",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_FREQUENCY_12M: A maximum of ONE (1) fee waiver is permitted "
            "per card member account per 12-month rolling period. If the customer has already "
            "received an approved fee waiver within the last 12 months, any new fee waiver "
            "request must be automatically DENIED. This applies to all fee types including "
            "late fees, annual fees, foreign transaction fees, and returned payment fees. "
            "The decision must be logged as a compliance event with the rule_id."
        )
    },
    {
        "id": "RULE_CREDIT_LIMIT_SCORE_700",
        "category": "credit_limit",
        "text": (
            "Rule RULE_CREDIT_LIMIT_SCORE_700: Credit Limit Increase (CLI) requests require "
            "a minimum FICO credit score of 701 or above. Requests from customers with a "
            "credit score of 700 or below must be DENIED. The denial reason must cite the "
            "credit score threshold. Additionally, the requested credit limit cannot exceed "
            "20% of the customer's stated annual income. Both conditions must be satisfied "
            "for approval."
        )
    },
    {
        "id": "RULE_CREDIT_LIMIT_INCOME_CAP",
        "category": "credit_limit",
        "text": (
            "Rule RULE_CREDIT_LIMIT_INCOME_CAP: The maximum approved credit limit is capped at "
            "20 percent (20%) of the customer's verified annual income. For example, a customer "
            "with annual income of $50,000 may receive a maximum credit limit of $10,000. "
            "Requests exceeding this income-based cap must be DENIED even if the credit score "
            "requirement is met. Partial approval up to the income cap is not permitted — "
            "the exact requested amount is either fully approved or denied."
        )
    },
    {
        "id": "RULE_CARD_FREEZE_LOST_STOLEN",
        "category": "card_replacement",
        "text": (
            "Rule RULE_CARD_FREEZE_LOST_STOLEN: When a card member reports a card as LOST, "
            "STOLEN, or compromised due to FRAUD, the existing card must be IMMEDIATELY "
            "frozen and cancelled before a replacement is dispatched. This is a mandatory "
            "security action with no exceptions. The card freeze must be logged as a "
            "HIGH severity event. Standard replacement processing time is 3-5 business days. "
            "Expedited shipping (1-2 business days) is available on request."
        )
    },
    {
        "id": "RULE_CARD_REPLACEMENT_STANDARD",
        "category": "card_replacement",
        "text": (
            "Rule RULE_CARD_REPLACEMENT_STANDARD: Replacement cards for DAMAGED or EXPIRED "
            "cards do not require the existing card to be frozen. The customer's account "
            "remains active throughout the replacement process. Standard delivery is "
            "3-5 business days. The replacement must be dispatched to the verified address "
            "on file or a new address provided by the authenticated customer in this session."
        )
    },
    {
        "id": "RULE_TRAVEL_NOTIFICATION",
        "category": "travel",
        "text": (
            "Rule RULE_TRAVEL_NOTIFICATION: Card members may register travel notifications "
            "for international or domestic travel to prevent fraudulent transaction blocks. "
            "Once a travel notification is set, the fraud detection system (rule "
            "FRAUD-RULE-TRAVEL-PASSTHRU-009) will allow transactions from the specified "
            "destination country/region for the stated date range. Travel notifications "
            "must include: destination, travel start date, and travel end date. There is "
            "no limit on the number of travel notifications a customer may set."
        )
    },
    {
        "id": "RULE_HUMAN_ESCALATION",
        "category": "escalation",
        "text": (
            "Rule RULE_HUMAN_ESCALATION: The AI agent must escalate to a human supervisor "
            "when: (1) the customer explicitly requests to speak with a human agent, "
            "(2) the customer's frustration score exceeds 0.85, (3) the request falls "
            "outside the agent's defined service scope, or (4) a compliance rule has been "
            "triggered 2 or more times in the same session. Upon escalation, the agent "
            "must provide a complete context handoff summary including account_id, "
            "session history, intent detected, and reason for escalation."
        )
    },
    {
        "id": "RULE_ACCOUNT_STATUS_CHECK",
        "category": "general",
        "text": (
            "Rule RULE_ACCOUNT_STATUS_CHECK: Before executing any financial action (fee waiver, "
            "credit limit increase, card replacement), the agent must verify that the customer's "
            "account status is ACTIVE. Requests from accounts with status SUSPENDED, CLOSED, "
            "or FROZEN must be declined and the customer must be informed of their account "
            "status. The agent should offer to transfer to a human agent for account status "
            "resolution."
        )
    },
    {
        "id": "RULE_AUTHENTICATION_REQUIRED",
        "category": "general",
        "text": (
            "Rule RULE_AUTHENTICATION_REQUIRED: All financial service requests must only be "
            "processed for authenticated card members whose identity has been verified in the "
            "current session. The account_id must be present in the session context. The agent "
            "must never perform financial actions on behalf of an unauthenticated or unknown "
            "account. If account_id is missing or unverifiable, the agent must decline and "
            "prompt for authentication."
        )
    },
]

# Sarvam-supported language codes for reference
SARVAM_SUPPORTED_LANGUAGES = {
    "hi-IN": "Hindi",
    "bn-IN": "Bengali",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
    "en-IN": "English (India)",
    "en-US": "English (US)",
}
