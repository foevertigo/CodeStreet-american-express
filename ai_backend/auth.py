"""
auth.py — Authentication & Customer Profile Manager (with DB Fallback)
"""

import logging
from typing import Optional, Any
from audit_service.postgres_client import PostgresClient, get_db_cursor

logger = logging.getLogger(__name__)

MOCK_CUSTOMERS = [
    {
        "account_id": "a1111111-0000-0000-0000-000000000001",
        "first_name": "James",
        "last_name": "Wilson",
        "email": "j.wilson@example.com",
        "phone_number": "+12025550001",
        "account_status": "active",
        "credit_score": 750,
        "annual_income": 120000.0,
        "credit_limit": 25000.0,
        "current_balance": 1820.49,
        "address_line1": "742 Evergreen Terrace",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62701",
        "waivers_last_year": 1  # INELIGIBLE for fee waiver
    },
    {
        "account_id": "a2222222-0000-0000-0000-000000000002",
        "first_name": "Sarah",
        "last_name": "Chen",
        "email": "s.chen@example.com",
        "phone_number": "+12025550002",
        "account_status": "active",
        "credit_score": 620,
        "annual_income": 48000.0,
        "credit_limit": 3000.0,
        "current_balance": 2815.12,
        "address_line1": "100 Market St",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "waivers_last_year": 0  # ELIGIBLE for fee waiver, CLI INELIGIBLE (<700)
    },
    {
        "account_id": "a3333333-0000-0000-0000-000000000003",
        "first_name": "Marcus",
        "last_name": "Johnson",
        "email": "m.johnson@example.com",
        "phone_number": "+12025550003",
        "account_status": "active",
        "credit_score": 810,
        "annual_income": 250000.0,
        "credit_limit": 50000.0,
        "current_balance": 5390.00,
        "address_line1": "55 Wall Street",
        "city": "New York",
        "state": "NY",
        "zip_code": "10005",
        "waivers_last_year": 0  # ELIGIBLE FOR ALL
    },
    {
        "account_id": "a4444444-0000-0000-0000-000000000004",
        "first_name": "Emily",
        "last_name": "Rodriguez",
        "email": "e.rodriguez@example.com",
        "phone_number": "+12025550004",
        "account_status": "active",
        "credit_score": 580,
        "annual_income": 35000.0,
        "credit_limit": 1500.0,
        "current_balance": 115.00,
        "address_line1": "456 Oak Lane",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "waivers_last_year": 0
    },
    {
        "account_id": "a5555555-0000-0000-0000-000000000005",
        "first_name": "David",
        "last_name": "Kim",
        "email": "d.kim@example.com",
        "phone_number": "+12025550005",
        "account_status": "suspended",
        "credit_score": 490,
        "annual_income": 28000.0,
        "credit_limit": 500.0,
        "current_balance": 495.00,
        "address_line1": "789 Pine St",
        "city": "Seattle",
        "state": "WA",
        "zip_code": "98101",
        "waivers_last_year": 0
    }
]


def get_customer_profile(account_id: str) -> Optional[dict[str, Any]]:
    """
    Fetches full customer profile by account_id from Postgres, with mock fallback.
    """
    try:
        client = PostgresClient()
        cust = client.get_customer(account_id)
        if cust:
            return cust
    except Exception as e:
        logger.warning(f"Postgres get_customer query error ({e}). Using mock customer store.")
    
    for c in MOCK_CUSTOMERS:
        if c["account_id"] == account_id:
            return c
    return None


def list_demo_customers() -> list[dict[str, Any]]:
    """
    Returns seeded customer profiles for frontend dropdown selection.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT 
                    account_id::text, first_name, last_name, email, phone_number,
                    account_status, credit_score, annual_income, credit_limit,
                    current_balance, address_line1, city, state, zip_code
                FROM customers
                ORDER BY account_id ASC
            """)
            rows = cur.fetchall()
            if rows:
                return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Postgres list_demo_customers error ({e}). Returning fallback demo profiles.")
    
    return MOCK_CUSTOMERS
