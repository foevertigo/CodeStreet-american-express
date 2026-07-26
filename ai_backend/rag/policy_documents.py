"""
policy_documents.py — Authoritative compliance rule text (single source of truth).
The RAG engine ingests these at startup. The LLM only quotes from these chunks —
zero hallucinated policy content. All numeric thresholds are also exposed in a
`params` dict on each rule so the deterministic Python layer (never the LLM)
performs the actual eligibility math and returns a decision + rule_id.

NOTE (PROTOTYPE DISCLAIMER):
This rule set is SYNTHETIC and built only for demoing the pipeline end-to-end.
It intentionally does NOT model any real issuer's actual policy, underwriting
criteria, or legal/regulatory language. Numbers (60%, 701, 20%, etc.) are
illustrative placeholders chosen to be internally consistent and testable —
not sourced from any real card program. Swap them out before this touches
anything resembling production or real customer data.
"""

COMPLIANCE_RULES = [

    # ------------------------------------------------------------------
    # FEE WAIVER — routing table (read this first)
    # ------------------------------------------------------------------
    {
        "id": "RULE_FEE_WAIVER_TYPE_ROUTING",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_TYPE_ROUTING: Fee waiver requests must be routed by "
            "fee_type before any other rule is applied. (1) fee_type = ANNUAL_FEE is "
            "evaluated under RULE_FEE_WAIVER_ANNUAL_SPEND_60 first; if that rule does not "
            "produce an approval, fall back to RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M. "
            "(2) fee_type in {LATE_FEE, FOREIGN_TRANSACTION_FEE, RETURNED_PAYMENT_FEE} is "
            "evaluated only under RULE_FEE_WAIVER_NON_ANNUAL_12M. (3) If fee_type is missing, "
            "unrecognized, or ambiguous, the agent must not guess — it must ask the customer "
            "to confirm which fee they mean before evaluating any waiver rule. Only one "
            "waiver decision path may apply per request; the agent must not evaluate a "
            "request under more than one fee_type category."
        ),
        "params": {
            "fee_types": {
                "ANNUAL_FEE": ["RULE_FEE_WAIVER_ANNUAL_SPEND_60", "RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M"],
                "LATE_FEE": ["RULE_FEE_WAIVER_NON_ANNUAL_12M"],
                "FOREIGN_TRANSACTION_FEE": ["RULE_FEE_WAIVER_NON_ANNUAL_12M"],
                "RETURNED_PAYMENT_FEE": ["RULE_FEE_WAIVER_NON_ANNUAL_12M"],
            }
        }
    },

    # ------------------------------------------------------------------
    # FEE WAIVER — annual fee, spend-based (primary path)
    # ------------------------------------------------------------------
    {
        "id": "RULE_FEE_WAIVER_ANNUAL_SPEND_60",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_ANNUAL_SPEND_60: An ANNUAL_FEE waiver is automatically "
            "APPROVED, independent of prior waiver history, if the card member's total "
            "verified spend in the current membership year is greater than or equal to "
            "60% of their assigned credit limit (spend_ratio >= 0.60). Spend is measured "
            "as posted purchase transactions only; cash advances, balance transfers, fees, "
            "interest, and reversed/refunded transactions are excluded from the spend "
            "calculation. If spend_ratio >= 0.60, the agent must approve the waiver and "
            "log the decision with spend_ratio as evidence — no further checks apply and "
            "RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M is not evaluated. If spend_ratio < 0.60, "
            "the agent must fall through to RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M rather "
            "than denying outright."
        ),
        "params": {"fee_type": "ANNUAL_FEE", "spend_ratio_threshold": 0.60, "comparator": ">="}
    },
    {
        "id": "RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_ANNUAL_FREQUENCY_12M: If an ANNUAL_FEE waiver request does "
            "not qualify under RULE_FEE_WAIVER_ANNUAL_SPEND_60 (spend_ratio < 0.60), it may "
            "still be approved if the card member has NOT received an approved annual fee "
            "waiver within the trailing 12 months, up to a maximum of ONE (1) such waiver "
            "per 12-month rolling period. If an annual fee waiver was already approved within "
            "the last 12 months, the new request must be DENIED regardless of spend. The "
            "denial reason must state both the spend shortfall and the frequency cap so the "
            "customer understands both conditions that were checked."
        ),
        "params": {"fee_type": "ANNUAL_FEE", "waiver_cap_per_12_months": 1}
    },

    # ------------------------------------------------------------------
    # FEE WAIVER — everything that is NOT the annual fee
    # ------------------------------------------------------------------
    {
        "id": "RULE_FEE_WAIVER_NON_ANNUAL_12M",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_NON_ANNUAL_12M: For LATE_FEE, FOREIGN_TRANSACTION_FEE, and "
            "RETURNED_PAYMENT_FEE, the spend-based waiver in RULE_FEE_WAIVER_ANNUAL_SPEND_60 "
            "NEVER applies — spend ratio is not a valid basis for waiving these fees under "
            "any circumstance. Instead, a maximum of ONE (1) waiver across these three fee "
            "types combined is permitted per card member account per 12-month rolling period. "
            "If any waiver of any of these three fee types was approved within the last 12 "
            "months, a new request for any of them must be DENIED. If none was approved in "
            "the trailing 12 months, the request may be APPROVED. The decision must be logged "
            "as a compliance event with the rule_id and the specific fee_type evaluated."
        ),
        "params": {
            "fee_types": ["LATE_FEE", "FOREIGN_TRANSACTION_FEE", "RETURNED_PAYMENT_FEE"],
            "waiver_cap_per_12_months_combined": 1
        }
    },

    # ------------------------------------------------------------------
    # FEE WAIVER — edge cases that must never fall through to a guess
    # ------------------------------------------------------------------
    {
        "id": "RULE_FEE_WAIVER_DATA_UNAVAILABLE",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_DATA_UNAVAILABLE: If the data required to evaluate a fee "
            "waiver is missing or unverifiable — spend history for ANNUAL_FEE requests, or "
            "prior waiver history for any fee type — the agent must NOT approve the waiver "
            "and must NOT assume a favorable value (e.g., must not assume spend_ratio is high "
            "or that no prior waiver exists). The request must be DENIED pending data "
            "verification, and the agent must inform the customer that the request requires "
            "additional verification. This is treated as a triggered compliance rule for the "
            "purposes of RULE_HUMAN_ESCALATION's 2-strike counter."
        ),
        "params": {}
    },
    {
        "id": "RULE_FEE_WAIVER_MULTI_REQUEST_SAME_SESSION",
        "category": "fee_waiver",
        "text": (
            "Rule RULE_FEE_WAIVER_MULTI_REQUEST_SAME_SESSION: If a customer requests waivers "
            "for more than one fee_type in the same session, each fee_type must be evaluated "
            "independently under its own rule from RULE_FEE_WAIVER_TYPE_ROUTING — an approval "
            "or denial on one fee_type must not be applied to another. Because "
            "RULE_FEE_WAIVER_NON_ANNUAL_12M shares its cap across LATE_FEE, "
            "FOREIGN_TRANSACTION_FEE, and RETURNED_PAYMENT_FEE, approving one of those three "
            "in this session immediately makes the other two in the same 12-month period "
            "ineligible and they must be denied without a separate lookup."
        ),
        "params": {}
    },

    # ------------------------------------------------------------------
    # CREDIT LIMIT INCREASE
    # ------------------------------------------------------------------
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
        ),
        "params": {"min_credit_score": 701}
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
        ),
        "params": {"income_cap_pct": 0.20}
    },
    {
        "id": "RULE_CREDIT_LIMIT_DATA_UNAVAILABLE",
        "category": "credit_limit",
        "text": (
            "Rule RULE_CREDIT_LIMIT_DATA_UNAVAILABLE: If credit score or annual income cannot "
            "be retrieved or verified for the authenticated customer, the CLI request must be "
            "DENIED — the agent must never assume a passing score or a favorable income figure. "
            "The customer must be informed that the request cannot be evaluated without "
            "verified data and offered escalation to a human agent."
        ),
        "params": {}
    },

    # ------------------------------------------------------------------
    # CARD REPLACEMENT
    # ------------------------------------------------------------------
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
        ),
        "params": {"standard_days": "3-5", "expedited_days": "1-2"}
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
        ),
        "params": {"standard_days": "3-5"}
    },
    {
        "id": "RULE_CARD_REPLACEMENT_REPEAT_REQUEST",
        "category": "card_replacement",
        "text": (
            "Rule RULE_CARD_REPLACEMENT_REPEAT_REQUEST: If this is the third or more "
            "replacement request (any reason) for the same account within a 12-month rolling "
            "period, the agent must not auto-approve. The request must be flagged for human "
            "review and treated as a triggered compliance rule for RULE_HUMAN_ESCALATION's "
            "2-strike counter, since repeated replacements can indicate fraud."
        ),
        "params": {"repeat_threshold_12_months": 3}
    },

    # ------------------------------------------------------------------
    # TRAVEL NOTIFICATION
    # ------------------------------------------------------------------
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
        ),
        "params": {}
    },
    {
        "id": "RULE_TRAVEL_NOTIFICATION_DATE_VALIDATION",
        "category": "travel",
        "text": (
            "Rule RULE_TRAVEL_NOTIFICATION_DATE_VALIDATION: A travel notification's start date "
            "must not be in the past relative to the current session date, and the end date "
            "must be on or after the start date. Requests failing either check must be DENIED "
            "and the agent must ask the customer to provide corrected dates rather than "
            "silently adjusting them."
        ),
        "params": {}
    },

    # ------------------------------------------------------------------
    # ESCALATION & GATING RULES
    # ------------------------------------------------------------------
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
        ),
        "params": {"frustration_threshold": 0.85, "compliance_trigger_count": 2}
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
        ),
        "params": {"required_status": "ACTIVE"}
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
        ),
        "params": {}
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