# Integration Guide — Async Audit Pipeline & Databases

**Maintained by:** Audit Pipeline Team  
**Version:** 1.0.0

This document tells every other developer exactly how to connect to and use
the services owned by this component.

---

## Prerequisites

1. **Docker Desktop** must be running on your machine.
2. Clone this repo and navigate to the project folder.
3. Get the `.env` file (or copy `.env.example` → `.env`).
4. Run:
   ```bash
   docker compose up -d
   ```
5. Wait ~60 seconds for all services to start, then verify:
   ```bash
   docker compose ps
   ```
   All services should show `Up`.

---

## Service Endpoints

| Service | Host (from your Python app) | Port | Purpose |
|---|---|---|---|
| **Kafka** | `localhost` | `9092` | Publish audit events |
| **Redis** | `localhost` | `6379` | Session state |
| **PostgreSQL** | `localhost` | `5432` | Customer data |
| **Elasticsearch** | `localhost` | `9200` | Query audit logs |
| **Kibana** | `localhost` | `5601` | Dashboard UI |

---

## Installing the `audit_service` Package

Add this to your service's virtual environment:

```bash
pip install -r requirements.txt
```

Or just copy-install the dependencies manually:

```bash
pip install kafka-python redis psycopg2-binary pydantic pydantic-settings python-dotenv tenacity
```

Then make sure your service can import from `audit_service/` — either:
- Copy the `audit_service/` folder into your project, OR
- Add the path to your Python path in your entrypoint

---

## 1. Kafka — Publishing Audit Events

**Who uses this:** LangGraph Orchestrator, Policy Engine, Banking API, Auth Manager

### The Golden Rule
> **Never** construct raw JSON and send to Kafka directly.  
> Always use the Pydantic event schemas. They enforce structure and add event_id automatically.

### Import Pattern

```python
from audit_service.kafka_producer import publish_event
from audit_service.event_schemas import FeeWaiverEvent, EventDecision
```

### Examples for Each Microservice

#### LangGraph Orchestrator — After a fee waiver is processed:
```python
from audit_service.kafka_producer import publish_event
from audit_service.event_schemas import FeeWaiverEvent, EventDecision

event = FeeWaiverEvent(
    session_id=state["session_id"],
    account_id=state["authenticated_user_id"],
    fee_type="late_fee",
    amount_requested=35.00,
    amount_approved=35.00,          # 0.0 if denied
    decision=EventDecision.APPROVED,
    agent_reasoning="Customer eligible: no prior waiver in 12 months.",
    transaction_id="txn-bank-ref-001",
    policy_version="v1.0",
)
result = publish_event(event)
# Returns: {"success": True, "topic": "agent-actions", "event_id": "...", "partition": 0, "offset": 42}
```

#### Policy Engine — After every compliance check:
```python
from audit_service.event_schemas import ComplianceDecisionEvent, EventDecision

event = ComplianceDecisionEvent(
    session_id=session_id,
    account_id=account_id,
    rule_id="RULE_FEE_WAIVER_FREQUENCY_4.1",
    rule_description="Customer may only receive 1 fee waiver per 12 months",
    decision=EventDecision.DENIED,
    denial_reason="Customer already received a waiver on 2024-04-20",
    input_data={"waivers_last_year": 1, "last_waiver_date": "2024-04-20"},
    output_data={"eligible": False},
    policy_version="v1.0",
)
publish_event(event)
```

#### Any Service — On unhandled exception:
```python
from audit_service.event_schemas import SystemErrorEvent
import traceback

try:
    result = call_banking_api(...)
except Exception as e:
    from audit_service.kafka_producer import publish_event
    publish_event(SystemErrorEvent(
        session_id=session_id,
        error_type=type(e).__name__,
        error_message=str(e),
        stack_trace=traceback.format_exc(),
        service_name="banking-api-connector",
        recovery_action="Initiated human handoff",
    ))
```

#### LangGraph — On human escalation:
```python
from audit_service.event_schemas import EscalationEvent, EscalationReason

publish_event(EscalationEvent(
    session_id=state["session_id"],
    account_id=state["authenticated_user_id"],
    reason=EscalationReason.POLICY_DENIED,
    original_intent=state["intent"],
    conversation_turns=len(state["messages"]),
    context_snapshot={
        "last_user_message": state["messages"][-1]["content"],
        "collected_entities": state.get("collected_entities", {}),
        "eligibility_status": state.get("eligibility_status"),
    }
))
```

### Available Event Types

| Event Class | Kafka Topic | Use When |
|---|---|---|
| `FeeWaiverEvent` | `agent-actions` | Fee waiver approved or denied |
| `ComplianceDecisionEvent` | `compliance-decisions` | ANY policy rule evaluation |
| `CreditLimitChangeEvent` | `agent-actions` | Credit limit change approved or denied |
| `CardReplacementEvent` | `card-events` | Card replacement initiated |
| `EscalationEvent` | `escalations` | Human handoff triggered |
| `SystemErrorEvent` | `system-errors` | Unhandled exception caught |
| `TravelNotificationEvent` | `agent-actions` | Travel notice set |

### Shutdown Hook (FastAPI)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from audit_service.kafka_producer import close_producer

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_producer()  # Flush remaining messages before shutdown

app = FastAPI(lifespan=lifespan)
```

---

## 2. Redis — Session State (LangGraph Orchestrator Only)

**Who uses this:** LangGraph Orchestrator

```python
from audit_service.redis_client import RedisSessionClient

session = RedisSessionClient()

# At start of each conversation turn — load existing state
state = session.get_session(session_id)
if state is None:
    # Session expired — re-authenticate
    state = initialize_new_state(session_id)

# After each LangGraph turn — save updated state
session.set_session(session_id, {
    "messages": state["messages"],
    "authenticated_user_id": "a1111111-...",
    "intent": "fee_waiver",
    "eligibility_status": None,     # Set by Policy Engine
    "requires_escalation": False,
    "collected_entities": {
        "fee_type": "late_fee",
        "amount": 35.0,
    }
})

# Quick field update (e.g., after Policy Engine responds)
session.update_session_field(session_id, "eligibility_status", "approved")

# On session end
session.delete_session(session_id)
```

### Recommended State Schema

```python
STATE_SCHEMA = {
    "session_id": str,                    # Same as Redis key
    "authenticated_user_id": str | None,  # Customer account_id UUID
    "channel": str,                        # "web" | "voice" | "mobile"
    "messages": list,                      # Full message history
    "intent": str | None,                 # Detected intent
    "collected_entities": dict,           # Variables gathered from user
    "eligibility_status": str | None,     # Set by Policy Engine
    "requires_escalation": bool,
    "turns": int,
}
```

---

## 3. PostgreSQL — Customer Data (Policy Engine + Auth Manager)

**Who uses this:** Policy Engine, Auth Manager, potentially LangGraph Orchestrator

```python
from audit_service.postgres_client import PostgresClient

db = PostgresClient()

# Auth Manager: Look up customer by phone (for voice ANI check)
customer = db.get_customer_by_phone("+12025550001")

# Policy Engine: Get full customer profile
customer = db.get_customer(account_id)
credit_score = customer["credit_score"]
annual_income = customer["annual_income"]
current_limit = customer["credit_limit"]

# Policy Engine: Check fee waiver eligibility
waiver_count = db.get_fee_waiver_count_last_year(account_id)
if waiver_count >= 1:
    # DENY — already used their annual waiver
    ...

# Policy Engine: Record the decision (ALWAYS call this, even on denial)
db.record_fee_waiver(
    account_id=account_id,
    fee_type="late_fee",
    amount_requested=35.00,
    amount_approved=35.00,      # 0.0 if denied
    decision="approved",        # or "denied"
    session_id=session_id,
    denial_reason=None,         # Required if denied
)

# Orchestrator: Start/end session tracking
db.start_agent_session(session_id, account_id, channel="voice")
# ... conversation ...
db.end_agent_session(session_id, outcome="resolved", intent_detected="fee_waiver", total_turns=4)
```

### Demo Customer UUIDs

| Customer | UUID | Credit Score | Scenario |
|---|---|---|---|
| James Wilson | `a1111111-0000-0000-0000-000000000001` | 750 | Fee waiver **INELIGIBLE** (used 3 months ago) |
| Sarah Chen | `a2222222-0000-0000-0000-000000000002` | 620 | Fee waiver eligible, CLI **INELIGIBLE** |
| Marcus Johnson | `a3333333-0000-0000-0000-000000000003` | 810 | Eligible for everything |
| Emily Rodriguez | `a4444444-0000-0000-0000-000000000004` | 580 | New account (Feb 2024) |
| David Kim | `a5555555-0000-0000-0000-000000000005` | 490 | **SUSPENDED** account |

---

## 4. Viewing Audit Logs in Kibana

1. Open [http://localhost:5601](http://localhost:5601)
2. Go to **Discover** → **Create data view**
3. Index pattern: `amex-audit-*`
4. Time field: `@timestamp`
5. Click **Save and open**

You can now search, filter, and build dashboards from all audit events.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Kafka connection refused` | Run `docker compose up -d` and wait 30s |
| `Redis connection refused` | Run `docker compose up -d kafka` |
| `psycopg2 connect failed` | `docker compose logs postgres` |
| Events not showing in Kibana | `docker compose logs logstash` — check for parse errors |
| `ModuleNotFoundError: audit_service` | Add project root to PYTHONPATH |

```bash
# Quick health check all at once
python scripts/verify_pipeline.py
```
