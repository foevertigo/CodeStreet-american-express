"""
seed_db.py — Inserts rich mock data for demo/development purposes.

Populates:
  - 5 customer profiles (covering all credit score scenarios)
  - Fee waiver history (so policy checks return realistic results)
  - Credit limit history
  - Sample transactions
  - Sample agent sessions

Run AFTER docker compose up -d and wait for Postgres to be healthy:
    python scripts/seed_db.py

Note: The basic INSERT in init.sql creates 5 customers.
This script adds richer historical data for a more realistic demo.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path so we can import audit_service
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from audit_service.postgres_client import PostgresClient, get_db_cursor

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def seed_fee_waiver_history(client: PostgresClient):
    """
    James Wilson (a111...) already used his waiver 3 months ago.
    → Policy Engine should DENY his next request.

    Sarah Chen (a222...) has never had a waiver.
    → Policy Engine should APPROVE her request.
    """
    logger.info("Seeding fee waiver history...")

    with get_db_cursor() as cur:
        # James: waiver 3 months ago (INELIGIBLE for another)
        cur.execute("""
            INSERT INTO fee_waiver_history
                (account_id, fee_type, amount_requested, amount_approved,
                 decision, policy_version, agent_session_id, created_at)
            VALUES
                ('a1111111-0000-0000-0000-000000000001', 'late_fee',
                 35.00, 35.00, 'approved', 'v1.0', 'sess-historical-001',
                 NOW() - INTERVAL '3 months')
            ON CONFLICT DO NOTHING
        """)

        # Emily Rodriguez: denied 2 months ago, no approved waiver
        cur.execute("""
            INSERT INTO fee_waiver_history
                (account_id, fee_type, amount_requested, amount_approved,
                 decision, denial_reason, policy_version, agent_session_id, created_at)
            VALUES
                ('a4444444-0000-0000-0000-000000000004', 'late_fee',
                 35.00, 0.00, 'denied',
                 'Customer account less than 6 months old', 'v1.0',
                 'sess-historical-002', NOW() - INTERVAL '2 months')
            ON CONFLICT DO NOTHING
        """)

    logger.info("  ✓ Fee waiver history seeded")


def seed_credit_limit_history(client: PostgresClient):
    """
    Marcus Johnson (a333...) got a limit increase 8 months ago (ELIGIBLE for another).
    Sarah Chen (a222...) got denied 1 month ago (within 6-month window = INELIGIBLE).
    """
    logger.info("Seeding credit limit history...")

    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO credit_limit_history
                (account_id, previous_limit, requested_limit, approved_limit,
                 decision, credit_score_at_decision, income_reported,
                 policy_version, agent_session_id, created_at)
            VALUES
                -- Marcus: approved 8 months ago (eligible for another)
                ('a3333333-0000-0000-0000-000000000003',
                 30000.00, 50000.00, 50000.00, 'approved', 805, 250000.00,
                 'v1.0', 'sess-historical-003', NOW() - INTERVAL '8 months'),

                -- Sarah: denied 1 month ago (ineligible for 5 more months)
                ('a2222222-0000-0000-0000-000000000002',
                 3000.00, 8000.00, NULL, 'denied', 615, 48000.00,
                 'v1.0', 'sess-historical-004', NOW() - INTERVAL '1 month')
            ON CONFLICT DO NOTHING
        """)

    logger.info("  ✓ Credit limit history seeded")


def seed_transactions(client: PostgresClient):
    """Adds a realistic 30-day transaction history for demo customers."""
    logger.info("Seeding transactions...")

    transactions = [
        # James Wilson — typical month
        ("a1111111-0000-0000-0000-000000000001", "purchase", 1250.50, "Delta Airlines", "travel", "Flight NYC-LAX"),
        ("a1111111-0000-0000-0000-000000000001", "purchase", 89.99, "Netflix", "entertainment", "NETFLIX.COM"),
        ("a1111111-0000-0000-0000-000000000001", "purchase", 234.56, "Whole Foods", "groceries", "WFM #0123"),
        ("a1111111-0000-0000-0000-000000000001", "fee", 35.00, None, None, "Late payment fee"),
        ("a1111111-0000-0000-0000-000000000001", "payment", 500.00, None, None, "Online payment"),

        # Sarah Chen — near-limit
        ("a2222222-0000-0000-0000-000000000002", "purchase", 1199.00, "Best Buy", "electronics", "BEST BUY #1234"),
        ("a2222222-0000-0000-0000-000000000002", "purchase", 14.99, "Spotify", "entertainment", "SPOTIFY"),
        ("a2222222-0000-0000-0000-000000000002", "purchase", 67.89, "Shell", "fuel", "SHELL #9876"),

        # Marcus Johnson — high spender
        ("a3333333-0000-0000-0000-000000000003", "purchase", 4500.00, "Four Seasons", "hotel", "FOUR SEASONS NYC"),
        ("a3333333-0000-0000-0000-000000000003", "purchase", 890.00, "Tiffany & Co", "shopping", "TIFFANY 0056"),
        ("a3333333-0000-0000-0000-000000000003", "payment", 10000.00, None, None, "Full balance payment"),

        # Emily Rodriguez — new customer
        ("a4444444-0000-0000-0000-000000000004", "purchase", 45.00, "Uber", "transportation", "UBER* TRIP"),
        ("a4444444-0000-0000-0000-000000000004", "purchase", 35.00, "Starbucks", "food", "STARBUCKS #7654"),
        ("a4444444-0000-0000-0000-000000000004", "fee", 35.00, None, None, "Late payment fee - June"),

        # Alex Taylor — 4 months of transactions totaling $3,000.00 (Credit Limit: $1,400)
        # Month 4 (3 months ago): $850.00 | Month 3 (2 months ago): $650.00
        # Month 2 (1 month ago): $900.00  | Month 1 (Current month): $600.00
        # Total = $850 + $650 + $900 + $600 = $3,000.00 (Spend ratio: 214% >= 60%)
        ("a6666666-0000-0000-0000-000000000006", "purchase", 850.00, "Apple Store", "electronics", "iPad & Accessories (Month 4)"),
        ("a6666666-0000-0000-0000-000000000006", "purchase", 650.00, "Delta Air Lines", "travel", "Flight SF-NYC (Month 3)"),
        ("a6666666-0000-0000-0000-000000000006", "purchase", 900.00, "Amazon.com", "shopping", "Home & Office (Month 2)"),
        ("a6666666-0000-0000-0000-000000000006", "purchase", 600.00, "Target", "groceries", "Monthly Supplies (Month 1)"),
    ]

    with get_db_cursor() as cur:
        for txn in transactions:
            account_id, txn_type, amount, merchant, category, desc = txn
            cur.execute("""
                INSERT INTO transactions
                    (account_id, transaction_type, amount, merchant_name,
                     merchant_category, description, initiated_by)
                VALUES (%s, %s, %s, %s, %s, %s, 'customer')
            """, (account_id, txn_type, amount, merchant, category, desc))

    logger.info(f"  ✓ {len(transactions)} transactions seeded")


def seed_agent_sessions(client: PostgresClient):
    """Seeds some historical AI agent sessions for demo dashboards."""
    logger.info("Seeding agent session history...")

    sessions = [
        # Successful fee waiver resolution
        ("sess-demo-001", "a1111111-0000-0000-0000-000000000001",
         "web", "fee_waiver", "resolved", False, 4),
        # Escalated — customer too frustrated
        ("sess-demo-002", "a2222222-0000-0000-0000-000000000002",
         "voice", "limit_increase", "escalated", True, 8),
        # Card replacement success
        ("sess-demo-003", "a3333333-0000-0000-0000-000000000003",
         "web", "card_replacement", "resolved", False, 3),
        # Abandoned
        ("sess-demo-004", "a4444444-0000-0000-0000-000000000004",
         "mobile", "fee_waiver", "abandoned", False, 2),
    ]

    with get_db_cursor() as cur:
        for sess in sessions:
            sess_id, acct, channel, intent, outcome, escalated, turns = sess
            cur.execute("""
                INSERT INTO agent_sessions_audit
                    (session_id, account_id, channel, intent_detected,
                     outcome, escalated_to_human, total_turns,
                     started_at, ended_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                        NOW() - INTERVAL '1 day',
                        NOW() - INTERVAL '23 hours')
                ON CONFLICT (session_id) DO NOTHING
            """, (sess_id, acct, channel, intent, outcome, escalated, turns))

    logger.info(f"  ✓ {len(sessions)} agent sessions seeded")


def seed_alex_taylor_profile(client: PostgresClient):
    """Seeds Alex Taylor profile if not exists."""
    logger.info("Seeding Alex Taylor customer profile...")
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO customers (
                account_id, first_name, last_name, email, phone_number, date_of_birth,
                ssn_last_four, address_line1, city, state, zip_code,
                account_status, credit_score, annual_income, credit_limit,
                current_balance, account_opened_date
            ) VALUES (
                'a6666666-0000-0000-0000-000000000006',
                'Alex', 'Taylor', 'alex.taylor@demo.com', '+12025550006',
                '1994-06-18', '6789', '100 Financial Plaza', 'San Francisco', 'CA', '94104',
                'active', 720, 65000.00, 1400.00, 4850.00, NOW() - INTERVAL '4 months'
            )
            ON CONFLICT (account_id) DO NOTHING
        """)
    logger.info("  ✓ Alex Taylor customer profile seeded")


def main():
    logger.info("=" * 60)
    logger.info("AmEx Agent — Database Seeder")
    logger.info("=" * 60)

    client = PostgresClient()

    # Verify connectivity first
    if not client.health_check():
        logger.error("Cannot connect to PostgreSQL. Is Docker running?")
        logger.error("Run: docker compose up -d && wait 30 seconds, then retry.")
        sys.exit(1)

    logger.info("PostgreSQL connection OK. Starting seed...")

    seed_alex_taylor_profile(client)
    seed_fee_waiver_history(client)
    seed_credit_limit_history(client)
    seed_transactions(client)
    seed_agent_sessions(client)

    logger.info("=" * 60)
    logger.info("Seed complete! Database is ready for demo.")
    logger.info("")
    logger.info("Test accounts:")
    logger.info("  James Wilson   (a111...) credit_score=750 — FEE WAIVER INELIGIBLE (used 3mo ago)")
    logger.info("  Sarah Chen     (a222...) credit_score=620 — FEE WAIVER ELIGIBLE, CLI INELIGIBLE")
    logger.info("  Marcus Johnson (a333...) credit_score=810 — ELIGIBLE for everything")
    logger.info("  Emily Rodriguez(a444...) credit_score=580 — NEW ACCOUNT (opened Feb 2024)")
    logger.info("  David Kim      (a555...) credit_score=490 — SUSPENDED account")
    logger.info("  Alex Taylor    (a666...) credit_score=720 — Limit: $1,400 | 4mo Spend: $3,000 (SPEND-BASED WAIVER ELIGIBLE)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
