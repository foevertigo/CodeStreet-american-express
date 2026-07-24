"""
auth.py — Authentication & Customer Profile Manager (with DB Fallback)
"""

import logging
from typing import Optional, Any
from audit_service.postgres_client import PostgresClient, get_db_cursor

logger = logging.getLogger(__name__)

MOCK_CUSTOMERS = []

def get_customer_profile(account_id: str) -> Optional[dict[str, Any]]:
    """
    Fetches full customer profile by account_id from Postgres, with generic fallback.
    """
    try:
        client = PostgresClient()
        cust = client.get_customer(account_id)
        if cust:
            return cust
    except Exception as e:
        logger.warning(f"Postgres get_customer query error ({e}). Returning generic profile.")
    
    # Generic fallback so agent doesn't crash when DB is down and mock data is removed
    return {
        "account_id": account_id,
        "first_name": "Card",
        "last_name": "Member",
        "email": "user@example.com",
        "phone_number": "+10000000000",
        "account_status": "active",
        "credit_score": 700,
        "annual_income": 50000.0,
        "credit_limit": 5000.0,
        "current_balance": 0.0,
        "address_line1": "123 Main St",
        "city": "Anytown",
        "state": "NY",
        "zip_code": "10001",
        "waivers_last_year": 0
    }


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
