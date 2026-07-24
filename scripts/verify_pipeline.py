"""
verify_pipeline.py — End-to-end pipeline integration test.

This script:
1. Verifies Redis is healthy
2. Verifies PostgreSQL is healthy
3. Publishes one event of EACH type to Kafka
4. Waits for Logstash to process them
5. Queries Elasticsearch to confirm they arrived
6. Prints a pass/fail report

Run AFTER docker compose up -d (wait ~60 seconds for all services to start):
    python scripts/verify_pipeline.py

Expected output:
    ✅ Redis: HEALTHY
    ✅ PostgreSQL: HEALTHY
    ✅ Elasticsearch: HEALTHY
    ✅ Kafka: Published 5 test events
    ⏳ Waiting 15s for Logstash to process...
    ✅ Elasticsearch: Found 5/5 events
    ✅ PIPELINE IS FULLY OPERATIONAL
"""

import sys
import time
import logging
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from audit_service.config import get_settings
from audit_service.redis_client import RedisSessionClient
from audit_service.postgres_client import PostgresClient
from audit_service.kafka_producer import publish_event, close_producer
from audit_service.event_schemas import (
    FeeWaiverEvent, ComplianceDecisionEvent, CreditLimitChangeEvent,
    CardReplacementEvent, EscalationEvent, SystemErrorEvent,
    EventDecision, CardReplacementReason, EscalationReason
)

logging.basicConfig(level=logging.WARNING)  # Suppress verbose logs during verify

settings = get_settings()

PASS = "✅"
FAIL = "❌"
WAIT = "⏳"

results = []


def check(name: str, ok: bool, detail: str = ""):
    icon = PASS if ok else FAIL
    msg = f"{icon} {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    results.append(ok)
    return ok


def verify_redis() -> bool:
    try:
        client = RedisSessionClient()
        # Test write and read
        client.set_session("verify-test-session", {"test": True, "pipeline_verify": "ok"})
        state = client.get_session("verify-test-session")
        client.delete_session("verify-test-session")
        if state and state.get("test") is True:
            return check("Redis", True, "Write/Read/Delete OK")
        return check("Redis", False, "Read returned wrong data")
    except Exception as e:
        return check("Redis", False, str(e))


def verify_postgres() -> bool:
    try:
        client = PostgresClient()
        ok = client.health_check()
        if ok:
            # Also verify we can query the seed data
            customer = client.get_customer("a1111111-0000-0000-0000-000000000001")
            if customer:
                return check("PostgreSQL", True, f"Schema OK, found customer: {customer['first_name']} {customer['last_name']}")
            return check("PostgreSQL", True, "Connected but no seed data (run seed_db.py)")
        return check("PostgreSQL", False, "Health check failed")
    except Exception as e:
        return check("PostgreSQL", False, str(e))


def verify_elasticsearch() -> bool:
    try:
        resp = requests.get(f"{settings.elasticsearch_url}/_cluster/health", timeout=5)
        data = resp.json()
        status = data.get("status")
        if status in ("green", "yellow"):
            return check("Elasticsearch", True, f"Cluster status: {status}")
        return check("Elasticsearch", False, f"Bad cluster status: {status}")
    except Exception as e:
        return check("Elasticsearch", False, str(e))


def publish_test_events() -> list[str]:
    """Publishes one of each event type and returns their event_ids."""
    print(f"\n{WAIT} Publishing test events to Kafka...")

    test_session = "verify-pipeline-session"
    test_account = "a1111111-0000-0000-0000-000000000001"
    event_ids = []

    events_to_publish = [
        FeeWaiverEvent(
            session_id=test_session, account_id=test_account,
            fee_type="late_fee", amount_requested=35.00,
            decision=EventDecision.APPROVED, amount_approved=35.00,
            agent_reasoning="[PIPELINE VERIFY] Test event",
        ),
        ComplianceDecisionEvent(
            session_id=test_session, account_id=test_account,
            rule_id="VERIFY-RULE-001",
            rule_description="[PIPELINE VERIFY] Test compliance event",
            decision=EventDecision.APPROVED,
            input_data={"credit_score": 750}, output_data={"eligible": True},
        ),
        CreditLimitChangeEvent(
            session_id=test_session, account_id=test_account,
            previous_limit=10000.00, requested_limit=15000.00,
            decision=EventDecision.APPROVED, approved_limit=15000.00,
            credit_score_used=750, income_reported=95000.00,
        ),
        CardReplacementEvent(
            session_id=test_session, account_id=test_account,
            reason=CardReplacementReason.DAMAGED,
            old_card_last_four="1234",
            shipping_address="[PIPELINE VERIFY] 742 Evergreen Terrace",
            old_card_cancelled=False,
        ),
        EscalationEvent(
            session_id=test_session, account_id=test_account,
            reason=EscalationReason.COMPLEX_QUERY,
            original_intent="fee_waiver",
            conversation_turns=5,
            context_snapshot={"pipeline_verify": True},
        ),
        SystemErrorEvent(
            session_id=test_session,
            error_type="PipelineVerificationError",
            error_message="[PIPELINE VERIFY] This is a test error event",
            service_name="verify_pipeline.py",
        ),
    ]

    success_count = 0
    for event in events_to_publish:
        try:
            result = publish_event(event)
            event_ids.append(event.event_id)
            success_count += 1
            print(f"   → Published {event.__class__.__name__} to '{result['topic']}' "
                  f"[partition={result['partition']}, offset={result['offset']}]")
        except Exception as e:
            print(f"   {FAIL} Failed to publish {event.__class__.__name__}: {e}")

    check("Kafka", success_count == len(events_to_publish),
          f"Published {success_count}/{len(events_to_publish)} test events")

    close_producer()
    return event_ids


def verify_elasticsearch_received(event_ids: list[str], wait_seconds: int = 45) -> bool:
    """Waits for Logstash to process events, then queries ES to confirm."""
    print(f"\n{WAIT} Waiting {wait_seconds}s for Logstash to process events...")
    time.sleep(wait_seconds)

    found = 0
    not_found = []

    for event_id in event_ids:
        try:
            resp = requests.get(
                f"{settings.elasticsearch_url}/amex-audit-*/_search",
                json={"query": {"term": {"event_id.keyword": event_id}}},
                timeout=10,
            )
            hits = resp.json().get("hits", {}).get("total", {}).get("value", 0)
            if hits > 0:
                found += 1
            else:
                not_found.append(event_id[:8] + "...")
        except Exception as e:
            not_found.append(f"ERROR: {e}")

    if not_found:
        return check(
            "Elasticsearch ingestion",
            False,
            f"Found {found}/{len(event_ids)} events. Missing: {not_found}"
        )
    return check(
        "Elasticsearch ingestion",
        True,
        f"All {found}/{len(event_ids)} events found in indices"
    )


def main():
    print("=" * 60)
    print("AmEx Agent — End-to-End Pipeline Verification")
    print("=" * 60)
    print()

    # Step 1: Health checks
    print("── Health Checks ──────────────────────────────────────────")
    redis_ok = verify_redis()
    pg_ok = verify_postgres()
    es_ok = verify_elasticsearch()

    if not all([redis_ok, pg_ok, es_ok]):
        print(f"\n{FAIL} Some services are not healthy. Ensure docker compose up -d has been run.")
        print("Run: docker compose ps  to see service statuses.")
        sys.exit(1)

    # Step 2: Publish events to Kafka
    print("\n── Kafka + Logstash Test ───────────────────────────────────")
    try:
        event_ids = publish_test_events()
    except Exception as e:
        check("Kafka", False, f"Could not connect to Kafka: {e}")
        print(f"\n{FAIL} Kafka is not reachable. Check docker compose logs kafka")
        sys.exit(1)

    # Step 3: Verify Elasticsearch received the events via Logstash
    print("\n── Elasticsearch Ingestion Verification ────────────────────")
    es_ingestion_ok = verify_elasticsearch_received(event_ids, wait_seconds=20)

    # Final report
    total_checks = len(results)
    passed = sum(results)
    print("\n" + "=" * 60)
    if all(results):
        print(f"{PASS} PIPELINE IS FULLY OPERATIONAL ({passed}/{total_checks} checks passed)")
        print(f"\n🔍 View audit logs at: http://localhost:5601 (Kibana)")
        print(f"   Index pattern: amex-audit-*")
    else:
        print(f"{FAIL} PIPELINE HAS ISSUES ({passed}/{total_checks} checks passed)")
        print("   Check: docker compose logs logstash")
    print("=" * 60)


if __name__ == "__main__":
    main()
