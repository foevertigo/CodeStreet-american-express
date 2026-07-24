"""
postgres_client.py — Customer & Transaction Database Interface.

Provides typed query functions for all teams to read customer data
and record financial actions.

This is what the Policy Engine team uses to:
  1. Look up a customer's credit score, income, limit (for CLI decisions)
  2. Check fee waiver history (for frequency checks)
  3. Record approved actions (fee waivers, limit changes, card replacements)

Usage:
    from audit_service.postgres_client import PostgresClient

    client = PostgresClient()

    # Policy Engine: check if customer is eligible for fee waiver
    customer = client.get_customer("a1111111-0000-0000-0000-000000000001")
    waivers = client.get_fee_waiver_count_last_year(customer["account_id"])

    if waivers == 0 and customer["account_status"] == "active":
        # Approve!
        client.record_fee_waiver(
            account_id=customer["account_id"],
            fee_type="late_fee",
            amount_requested=35.00,
            amount_approved=35.00,
            decision="approved",
            session_id="sess-xyz"
        )
"""

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Generator, Optional

import psycopg2
import psycopg2.extras
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from audit_service.config import get_settings

logger = logging.getLogger(__name__)

# Register UUID adapter so psycopg2 handles UUID objects natively
psycopg2.extras.register_uuid()


def _get_connection() -> psycopg2.extensions.connection:
    """
    Creates a new PostgreSQL connection.
    psycopg2 is synchronous — for production async use, swap with asyncpg.
    For a demo/hackathon, sync is perfectly fine.
    """
    settings = get_settings()
    conn = psycopg2.connect(
        settings.postgres_dsn,
        cursor_factory=psycopg2.extras.RealDictCursor,  # Returns rows as dicts
    )
    conn.autocommit = False
    return conn


@contextmanager
def get_db_cursor() -> Generator[psycopg2.extensions.cursor, None, None]:
    """
    Context manager that provides a cursor and handles commit/rollback.

    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM customers WHERE account_id = %s", (aid,))
            row = cursor.fetchone()
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction rolled back: {e}")
        raise
    finally:
        conn.close()


class PostgresClient:
    """
    High-level interface for querying and updating the customer database.

    All methods return plain Python dicts (from RealDictCursor) so they're
    easy to pass directly to Pydantic models or JSON responses.
    """

    # -------------------------------------------------------------------------
    # CUSTOMER QUERIES
    # -------------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(psycopg2.OperationalError),
        reraise=True,
    )
    def get_customer(self, account_id: str) -> Optional[dict[str, Any]]:
        """
        Fetches a customer profile by account_id.

        Args:
            account_id: UUID string of the customer's account.

        Returns:
            Customer dict with all profile fields, or None if not found.

        Used by:
            - Policy Engine: to get credit_score, annual_income, credit_limit
            - Auth Manager: to verify account status
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    account_id::text, first_name, last_name, email, phone_number,
                    account_status, credit_score, annual_income, credit_limit,
                    current_balance, account_opened_date, last_payment_date,
                    address_line1, address_line2, city, state, zip_code
                FROM customers
                WHERE account_id = %s
                """,
                (account_id,)
            )
            row = cur.fetchone()
            if row is None:
                logger.warning(f"Customer not found: {account_id}")
                return None
            return dict(row)

    def get_customer_by_phone(self, phone_number: str) -> Optional[dict[str, Any]]:
        """
        Fetches a customer by phone number (used in voice auth flow — ANI check).

        Args:
            phone_number: E.164 format, e.g. "+12025550001"

        Returns:
            Customer dict or None.
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT account_id::text, first_name, last_name, account_status,
                       credit_score, annual_income, credit_limit
                FROM customers
                WHERE phone_number = %s
                """,
                (phone_number,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    # -------------------------------------------------------------------------
    # POLICY ENGINE QUERIES
    # -------------------------------------------------------------------------

    def get_fee_waiver_count_last_year(self, account_id: str) -> int:
        """
        Returns the number of APPROVED fee waivers in the last 12 months.

        Policy Rule 1: If count >= 1, the request must be DENIED.

        Args:
            account_id: Customer UUID string.

        Returns:
            Integer count (0 = eligible, >= 1 = ineligible).
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) as waiver_count
                FROM fee_waiver_history
                WHERE account_id = %s
                  AND decision = 'approved'
                  AND created_at > NOW() - INTERVAL '1 year'
                """,
                (account_id,)
            )
            row = cur.fetchone()
            return int(row["waiver_count"]) if row else 0

    def get_recent_limit_changes(self, account_id: str, months: int = 6) -> list[dict]:
        """
        Returns credit limit changes in the last N months.
        Policy rule: Max 1 increase per 6 months.

        Args:
            account_id: Customer UUID string.
            months:     Look-back window in months (default 6).

        Returns:
            List of change records.
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT change_id::text, decision, requested_limit,
                       approved_limit, created_at
                FROM credit_limit_history
                WHERE account_id = %s
                  AND decision = 'approved'
                  AND created_at > NOW() - INTERVAL '%s months'
                ORDER BY created_at DESC
                """,
                (account_id, months)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_recent_transactions(self, account_id: str, limit: int = 10) -> list[dict]:
        """
        Returns the most recent N transactions for a customer.
        Used for transaction inquiry ("what is this charge?").

        Args:
            account_id: Customer UUID string.
            limit:      Max transactions to return.

        Returns:
            List of transaction dicts, newest first.
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT transaction_id::text, transaction_type, amount,
                       merchant_name, merchant_category, description,
                       transaction_date, status
                FROM transactions
                WHERE account_id = %s
                ORDER BY transaction_date DESC
                LIMIT %s
                """,
                (account_id, limit)
            )
            return [dict(row) for row in cur.fetchall()]

    # -------------------------------------------------------------------------
    # WRITE OPERATIONS — called after policy engine approves an action
    # -------------------------------------------------------------------------

    def record_fee_waiver(
        self,
        account_id: str,
        fee_type: str,
        amount_requested: float,
        amount_approved: float,
        decision: str,
        session_id: str,
        denial_reason: Optional[str] = None,
        policy_version: str = "v1.0",
        transaction_id: Optional[str] = None,
    ) -> str:
        """
        Records a fee waiver decision (approved or denied) to the database.
        ALWAYS call this regardless of approval — we need the denial audit trail too.

        Args:
            account_id:       Customer UUID string.
            fee_type:         "late_fee" | "annual_fee" | "overdraft_fee"
            amount_requested: Dollar amount customer requested.
            amount_approved:  Actual amount approved (0.0 if denied).
            decision:         "approved" | "denied"
            session_id:       LangGraph session ID.
            denial_reason:    Required when decision="denied".
            policy_version:   Version of policy engine rules used.
            transaction_id:   Bank transaction ID (only if approved).

        Returns:
            waiver_id (UUID string) of the new record.
        """
        waiver_id = str(uuid.uuid4())
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO fee_waiver_history (
                    waiver_id, account_id, fee_type, amount_requested,
                    amount_approved, decision, denial_reason,
                    policy_version, agent_session_id, transaction_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    waiver_id, account_id, fee_type, amount_requested,
                    amount_approved, decision, denial_reason,
                    policy_version, session_id, transaction_id
                )
            )
        logger.info(
            f"Fee waiver recorded: {decision} | account={account_id} | "
            f"amount={amount_approved} | waiver_id={waiver_id}"
        )
        return waiver_id

    def record_credit_limit_change(
        self,
        account_id: str,
        previous_limit: float,
        requested_limit: float,
        decision: str,
        session_id: str,
        approved_limit: Optional[float] = None,
        denial_reason: Optional[str] = None,
        credit_score: Optional[int] = None,
        income_reported: Optional[float] = None,
        policy_version: str = "v1.0",
    ) -> str:
        """
        Records a credit limit change decision. Also updates the customer's
        actual credit_limit in the customers table if approved.

        Returns:
            change_id (UUID string) of the new record.
        """
        change_id = str(uuid.uuid4())
        with get_db_cursor() as cur:
            # 1. Record the decision in history
            cur.execute(
                """
                INSERT INTO credit_limit_history (
                    change_id, account_id, previous_limit, requested_limit,
                    approved_limit, decision, denial_reason,
                    credit_score_at_decision, income_reported,
                    policy_version, agent_session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    change_id, account_id, previous_limit, requested_limit,
                    approved_limit, decision, denial_reason,
                    credit_score, income_reported,
                    policy_version, session_id
                )
            )
            # 2. If approved, update the actual credit limit
            if decision == "approved" and approved_limit is not None:
                cur.execute(
                    """
                    UPDATE customers
                    SET credit_limit = %s
                    WHERE account_id = %s
                    """,
                    (approved_limit, account_id)
                )
                logger.info(
                    f"Credit limit updated: account={account_id} "
                    f"{previous_limit} → {approved_limit}"
                )
        return change_id

    def record_card_replacement(
        self,
        account_id: str,
        reason: str,
        old_card_last_four: str,
        shipping_address: str,
        session_id: str,
        expedited: bool = False,
    ) -> str:
        """
        Records a card replacement request.

        Returns:
            replacement_id (UUID string) of the new record.
        """
        replacement_id = str(uuid.uuid4())
        # Security: lost/stolen cards must cancel old number
        old_card_status = "cancelled" if reason in ("lost", "stolen", "fraud") else "active"

        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO card_replacements (
                    replacement_id, account_id, reason, old_card_last_four,
                    old_card_status, shipping_address, expedited_shipping,
                    status, agent_session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'requested', %s)
                """,
                (
                    replacement_id, account_id, reason, old_card_last_four,
                    old_card_status, shipping_address, expedited, session_id
                )
            )
        logger.info(
            f"Card replacement recorded: {reason} | account={account_id} | "
            f"old_card=****{old_card_last_four} | old_status={old_card_status}"
        )
        return replacement_id

    def start_agent_session(
        self,
        session_id: str,
        account_id: Optional[str] = None,
        channel: str = "web"
    ) -> None:
        """
        Creates a lightweight session record in Postgres.
        Call this when a new LangGraph session starts (alongside setting Redis state).

        Args:
            session_id: Same session_id used as Redis key.
            account_id: Customer UUID (may be None if not yet authenticated).
            channel:    "web" | "voice" | "mobile"
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_sessions_audit (session_id, account_id, channel)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                (session_id, account_id, channel)
            )

    def end_agent_session(
        self,
        session_id: str,
        outcome: str,
        intent_detected: Optional[str] = None,
        total_turns: int = 0,
        escalated: bool = False,
    ) -> None:
        """
        Closes a session record in Postgres with outcome.
        Call this when the conversation ends (resolved, escalated, or abandoned).

        Args:
            session_id:     Session to close.
            outcome:        "resolved" | "escalated" | "abandoned" | "error"
            intent_detected: Main intent the agent detected (e.g., "fee_waiver")
            total_turns:    How many conversation turns occurred.
            escalated:      True if handed off to a human.
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE agent_sessions_audit
                SET ended_at = NOW(),
                    outcome = %s,
                    intent_detected = %s,
                    total_turns = %s,
                    escalated_to_human = %s
                WHERE session_id = %s
                """,
                (outcome, intent_detected, total_turns, escalated, session_id)
            )

    def health_check(self) -> bool:
        """
        Runs a simple SELECT 1 to verify DB connectivity.
        Returns True if healthy.
        """
        try:
            with get_db_cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Postgres health check failed: {e}")
            return False
