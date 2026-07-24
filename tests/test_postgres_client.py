"""
test_postgres_client.py — Unit tests for the PostgreSQL client.

Uses mocking so tests run without a real database.

Run: pytest tests/test_postgres_client.py -v
"""

from unittest.mock import MagicMock, patch, call

import pytest

from audit_service.postgres_client import PostgresClient


@pytest.fixture
def mock_cursor():
    """A mock psycopg2 cursor."""
    return MagicMock()


@pytest.fixture
def mock_db(mock_cursor):
    """Patches get_db_cursor context manager."""
    with patch("audit_service.postgres_client.get_db_cursor") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_cursor


@pytest.fixture
def db_client():
    return PostgresClient()


class TestGetCustomer:

    def test_returns_customer_dict_when_found(self, db_client, mock_db):
        mock_db.fetchone.return_value = {
            "account_id": "a1111111-0000-0000-0000-000000000001",
            "first_name": "James",
            "last_name": "Wilson",
            "account_status": "active",
            "credit_score": 750,
            "annual_income": 95000.00,
            "credit_limit": 10000.00,
            "current_balance": 1250.00,
        }
        result = db_client.get_customer("a1111111-0000-0000-0000-000000000001")

        assert result is not None
        assert result["first_name"] == "James"
        assert result["credit_score"] == 750

    def test_returns_none_when_customer_not_found(self, db_client, mock_db):
        mock_db.fetchone.return_value = None

        result = db_client.get_customer("nonexistent-uuid")

        assert result is None

    def test_get_customer_by_phone(self, db_client, mock_db):
        mock_db.fetchone.return_value = {
            "account_id": "a2222222-0000-0000-0000-000000000002",
            "first_name": "Sarah",
            "last_name": "Chen",
            "account_status": "active",
        }
        result = db_client.get_customer_by_phone("+12025550002")

        assert result["first_name"] == "Sarah"
        # Verify phone was passed to query
        mock_db.execute.assert_called_once()
        query_args = mock_db.execute.call_args[0]
        assert "+12025550002" in str(query_args[1])


class TestPolicyEngineQueries:

    def test_fee_waiver_count_returns_zero_for_eligible_customer(self, db_client, mock_db):
        mock_db.fetchone.return_value = {"waiver_count": 0}

        count = db_client.get_fee_waiver_count_last_year("a3333333-0000-0000-0000-000000000003")

        assert count == 0

    def test_fee_waiver_count_returns_one_for_ineligible_customer(self, db_client, mock_db):
        mock_db.fetchone.return_value = {"waiver_count": 1}

        count = db_client.get_fee_waiver_count_last_year("a1111111-0000-0000-0000-000000000001")

        assert count == 1

    def test_get_recent_transactions_returns_list(self, db_client, mock_db):
        mock_db.fetchall.return_value = [
            {"transaction_id": "t1", "amount": 89.99, "merchant_name": "Amazon"},
            {"transaction_id": "t2", "amount": 35.00, "merchant_name": None},
        ]
        results = db_client.get_recent_transactions("a111-test")

        assert len(results) == 2
        assert results[0]["amount"] == 89.99

    def test_get_recent_limit_changes_returns_empty_list(self, db_client, mock_db):
        mock_db.fetchall.return_value = []

        results = db_client.get_recent_limit_changes("a111-test")

        assert results == []


class TestWriteOperations:

    def test_record_fee_waiver_approved(self, db_client, mock_db):
        waiver_id = db_client.record_fee_waiver(
            account_id="a1111111-0000-0000-0000-000000000001",
            fee_type="late_fee",
            amount_requested=35.00,
            amount_approved=35.00,
            decision="approved",
            session_id="sess-test",
            policy_version="v1.0",
        )
        # Should return a UUID string
        assert isinstance(waiver_id, str)
        assert len(waiver_id) == 36

    def test_record_fee_waiver_denied_with_reason(self, db_client, mock_db):
        waiver_id = db_client.record_fee_waiver(
            account_id="a1111111-0000-0000-0000-000000000001",
            fee_type="late_fee",
            amount_requested=35.00,
            amount_approved=0.0,
            decision="denied",
            session_id="sess-test",
            denial_reason="Already used fee waiver in the past 12 months.",
        )
        assert waiver_id is not None
        # Verify execute was called (once for insert)
        mock_db.execute.assert_called_once()

    def test_record_card_replacement_stolen_sets_cancelled_status(self, db_client, mock_db):
        db_client.record_card_replacement(
            account_id="a111-test",
            reason="stolen",
            old_card_last_four="1234",
            shipping_address="742 Evergreen Terrace",
            session_id="sess-card",
        )
        call_args = mock_db.execute.call_args[0]
        # The tuple of values passed to INSERT
        params = call_args[1]
        # old_card_status should be 'cancelled' for stolen reason
        assert "cancelled" in params

    def test_record_card_replacement_damaged_keeps_active_status(self, db_client, mock_db):
        db_client.record_card_replacement(
            account_id="a111-test",
            reason="damaged",
            old_card_last_four="5678",
            shipping_address="221B Baker Street",
            session_id="sess-card",
        )
        call_args = mock_db.execute.call_args[0]
        params = call_args[1]
        # old_card_status should be 'active' for damaged reason (no fraud risk)
        assert "active" in params

    def test_health_check_returns_true(self, db_client, mock_db):
        mock_db.fetchone.return_value = {"?column?": 1}
        # health_check runs SELECT 1 — just needs to not throw
        result = db_client.health_check()
        assert result is True
