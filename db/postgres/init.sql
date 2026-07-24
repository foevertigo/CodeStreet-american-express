-- =============================================================================
-- PostgreSQL Schema — FinTech AI Agent
-- Auto-executed by Docker on first container start.
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TABLE: customers
-- Central customer profile. Referenced by ALL other tables.
-- The Policy Engine queries this to check credit score, income, account status.
-- =============================================================================
CREATE TABLE IF NOT EXISTS customers (
    account_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name          VARCHAR(100)        NOT NULL,
    last_name           VARCHAR(100)        NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    phone_number        VARCHAR(20)         NOT NULL,
    date_of_birth       DATE                NOT NULL,
    ssn_last_four       CHAR(4)             NOT NULL,       -- Never store full SSN
    address_line1       VARCHAR(255)        NOT NULL,
    address_line2       VARCHAR(255),
    city                VARCHAR(100)        NOT NULL,
    state               CHAR(2)             NOT NULL,
    zip_code            VARCHAR(10)         NOT NULL,
    account_status      VARCHAR(20)         NOT NULL DEFAULT 'active'
                            CHECK (account_status IN ('active', 'suspended', 'closed')),
    credit_score        SMALLINT            NOT NULL DEFAULT 650
                            CHECK (credit_score BETWEEN 300 AND 850),
    annual_income       NUMERIC(12, 2)      NOT NULL DEFAULT 0,
    credit_limit        NUMERIC(10, 2)      NOT NULL DEFAULT 1000.00,
    current_balance     NUMERIC(10, 2)      NOT NULL DEFAULT 0.00,
    account_opened_date DATE                NOT NULL DEFAULT CURRENT_DATE,
    last_payment_date   DATE,
    created_at          TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE customers IS 'Central customer profile table. PII data — access restricted.';
COMMENT ON COLUMN customers.ssn_last_four IS 'Only last 4 digits stored. Full SSN in encrypted vault.';
COMMENT ON COLUMN customers.credit_score IS 'Internal credit score 300-850. Updated nightly by risk engine.';

-- Index for fast lookup by phone (used in voice auth flow)
CREATE INDEX idx_customers_phone ON customers(phone_number);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_status ON customers(account_status);

-- =============================================================================
-- TABLE: transactions
-- All financial transactions. Append-only (no updates/deletes for compliance).
-- =============================================================================
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          UUID            NOT NULL REFERENCES customers(account_id),
    transaction_type    VARCHAR(50)     NOT NULL
                            CHECK (transaction_type IN (
                                'purchase', 'payment', 'fee', 'fee_reversal',
                                'credit_adjustment', 'refund', 'interest_charge'
                            )),
    amount              NUMERIC(10, 2)  NOT NULL,
    merchant_name       VARCHAR(255),
    merchant_category   VARCHAR(100),
    description         TEXT,
    transaction_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    posted_date         TIMESTAMPTZ,
    status              VARCHAR(20)     NOT NULL DEFAULT 'posted'
                            CHECK (status IN ('pending', 'posted', 'disputed', 'reversed')),
    agent_session_id    VARCHAR(255),   -- Links to Redis session (for AI-initiated txns)
    initiated_by        VARCHAR(20)     NOT NULL DEFAULT 'system'
                            CHECK (initiated_by IN ('customer', 'agent_ai', 'system', 'fraud_team')),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE transactions IS 'Append-only financial transaction ledger. No UPDATE or DELETE allowed.';

CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_date ON transactions(transaction_date DESC);
CREATE INDEX idx_transactions_type ON transactions(transaction_type);
CREATE INDEX idx_transactions_session ON transactions(agent_session_id);

-- Rule to prevent updates/deletes (enforces immutability at DB level)
CREATE RULE no_update_transactions AS ON UPDATE TO transactions DO INSTEAD NOTHING;
CREATE RULE no_delete_transactions AS ON DELETE TO transactions DO INSTEAD NOTHING;

-- =============================================================================
-- TABLE: fee_waiver_history
-- Tracks every fee waiver request (approved AND denied).
-- Policy Engine queries this: "Has this customer had a waiver in last 12 months?"
-- =============================================================================
CREATE TABLE IF NOT EXISTS fee_waiver_history (
    waiver_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          UUID            NOT NULL REFERENCES customers(account_id),
    fee_type            VARCHAR(50)     NOT NULL
                            CHECK (fee_type IN ('late_fee', 'annual_fee', 'overdraft_fee', 'other')),
    amount_requested    NUMERIC(10, 2)  NOT NULL,
    amount_approved     NUMERIC(10, 2)  DEFAULT 0.00,
    decision            VARCHAR(10)     NOT NULL
                            CHECK (decision IN ('approved', 'denied')),
    denial_reason       VARCHAR(255),   -- Populated when decision = 'denied'
    policy_version      VARCHAR(20)     NOT NULL DEFAULT 'v1.0',
    agent_session_id    VARCHAR(255),   -- Links to the AI session that made the decision
    transaction_id      UUID            REFERENCES transactions(transaction_id), -- If approved
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fee_waiver_history IS 'Audit log of all fee waiver requests. Used by Policy Engine for frequency checks.';

CREATE INDEX idx_fee_waiver_account ON fee_waiver_history(account_id);
CREATE INDEX idx_fee_waiver_date ON fee_waiver_history(created_at DESC);
-- Partial index: only approved waivers
CREATE INDEX idx_fee_waiver_recent_approved ON fee_waiver_history(account_id, created_at)
    WHERE decision = 'approved';

-- =============================================================================
-- TABLE: credit_limit_history
-- Tracks all credit limit change requests.
-- Policy Engine queries this for rate-limiting (e.g., max 1 increase per 6 months).
-- =============================================================================
CREATE TABLE IF NOT EXISTS credit_limit_history (
    change_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          UUID            NOT NULL REFERENCES customers(account_id),
    previous_limit      NUMERIC(10, 2)  NOT NULL,
    requested_limit     NUMERIC(10, 2)  NOT NULL,
    approved_limit      NUMERIC(10, 2),            -- NULL if denied
    decision            VARCHAR(10)     NOT NULL
                            CHECK (decision IN ('approved', 'denied', 'pending_review')),
    denial_reason       VARCHAR(255),
    credit_score_at_decision SMALLINT,             -- Snapshot of score at time of decision
    income_reported     NUMERIC(12, 2),            -- What customer stated
    policy_version      VARCHAR(20)     NOT NULL DEFAULT 'v1.0',
    agent_session_id    VARCHAR(255),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE credit_limit_history IS 'Audit log of all credit limit change requests.';

CREATE INDEX idx_cli_account ON credit_limit_history(account_id);
CREATE INDEX idx_cli_date ON credit_limit_history(created_at DESC);

-- =============================================================================
-- TABLE: card_replacements
-- Tracks all card replacement requests with reason (critical for security).
-- =============================================================================
CREATE TABLE IF NOT EXISTS card_replacements (
    replacement_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          UUID            NOT NULL REFERENCES customers(account_id),
    reason              VARCHAR(20)     NOT NULL
                            CHECK (reason IN ('damaged', 'lost', 'stolen', 'expired', 'fraud')),
    old_card_last_four  CHAR(4)         NOT NULL,
    new_card_last_four  CHAR(4),                   -- Set when card is issued
    old_card_status     VARCHAR(20)     NOT NULL DEFAULT 'cancelled'
                            CHECK (old_card_status IN ('active', 'frozen', 'cancelled')),
    shipping_address    TEXT            NOT NULL,   -- Confirmed address at time of request
    expedited_shipping  BOOLEAN         NOT NULL DEFAULT FALSE,
    status              VARCHAR(30)     NOT NULL DEFAULT 'requested'
                            CHECK (status IN ('requested', 'processing', 'shipped', 'delivered', 'failed')),
    tracking_number     VARCHAR(100),
    agent_session_id    VARCHAR(255),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    shipped_at          TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ
);

COMMENT ON TABLE card_replacements IS 'Card issuance audit trail. Reason field determines security actions (lost/stolen = cancel old card number).';

CREATE INDEX idx_card_account ON card_replacements(account_id);
CREATE INDEX idx_card_date ON card_replacements(created_at DESC);

-- =============================================================================
-- TABLE: agent_sessions_audit
-- Lightweight audit of all AI agent sessions.
-- Links the agent's session_id (Redis key) to a customer and outcome.
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_sessions_audit (
    session_id          VARCHAR(255)    PRIMARY KEY,
    account_id          UUID            REFERENCES customers(account_id),
    channel             VARCHAR(20)     NOT NULL DEFAULT 'web'
                            CHECK (channel IN ('web', 'voice', 'mobile')),
    intent_detected     VARCHAR(100),   -- e.g., 'fee_waiver', 'limit_increase', 'card_replacement'
    outcome             VARCHAR(30)     CHECK (outcome IN ('resolved', 'escalated', 'abandoned', 'error')),
    escalated_to_human  BOOLEAN         NOT NULL DEFAULT FALSE,
    total_turns         SMALLINT        NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    duration_seconds    INTEGER         GENERATED ALWAYS AS (
                            EXTRACT(EPOCH FROM (ended_at - started_at))::INTEGER
                        ) STORED
);

COMMENT ON TABLE agent_sessions_audit IS 'Lightweight session tracker. Full session state lives in Redis; this is the permanent record.';

CREATE INDEX idx_session_account ON agent_sessions_audit(account_id);
CREATE INDEX idx_session_date ON agent_sessions_audit(started_at DESC);
CREATE INDEX idx_session_outcome ON agent_sessions_audit(outcome);

-- =============================================================================
-- FUNCTION: update_updated_at()
-- Auto-updates the updated_at column on any row change.
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- MOCK DATA — 5 demo customers for development/testing
-- Seeding covers: good credit, poor credit, new account, high income scenarios
-- (More detailed seeding done by scripts/seed_db.py)
-- =============================================================================
INSERT INTO customers (
    account_id, first_name, last_name, email, phone_number, date_of_birth,
    ssn_last_four, address_line1, city, state, zip_code,
    account_status, credit_score, annual_income, credit_limit,
    current_balance, account_opened_date
) VALUES
(
    'a1111111-0000-0000-0000-000000000001',
    'James', 'Wilson', 'james.wilson@demo.com', '+12025550001',
    '1985-03-15', '1234', '742 Evergreen Terrace', 'Springfield', 'IL', '62701',
    'active', 750, 95000.00, 10000.00, 1250.00, '2018-06-01'
),
(
    'a2222222-0000-0000-0000-000000000002',
    'Sarah', 'Chen', 'sarah.chen@demo.com', '+12025550002',
    '1992-07-22', '5678', '221B Baker Street', 'Chicago', 'IL', '60601',
    'active', 620, 48000.00, 3000.00, 2800.00, '2022-01-15'
),
(
    'a3333333-0000-0000-0000-000000000003',
    'Marcus', 'Johnson', 'marcus.j@demo.com', '+12025550003',
    '1978-11-30', '9012', '1600 Pennsylvania Ave', 'Washington', 'DC', '20500',
    'active', 810, 250000.00, 50000.00, 5000.00, '2010-03-20'
),
(
    'a4444444-0000-0000-0000-000000000004',
    'Emily', 'Rodriguez', 'emily.r@demo.com', '+12025550004',
    '1999-04-01', '3456', '4 Privet Drive', 'Austin', 'TX', '73301',
    'active', 580, 32000.00, 1500.00, 1400.00, '2024-02-01'
),
(
    'a5555555-0000-0000-0000-000000000005',
    'David', 'Kim', 'david.kim@demo.com', '+12025550005',
    '1990-09-14', '7890', '10 Downing Street', 'New York', 'NY', '10001',
    'suspended', 490, 55000.00, 2000.00, 1900.00, '2020-08-10'
);

-- Insert some fee waiver history for James (already used his waiver this year)
INSERT INTO fee_waiver_history (account_id, fee_type, amount_requested, amount_approved, decision, policy_version, created_at)
VALUES (
    'a1111111-0000-0000-0000-000000000001',
    'late_fee', 35.00, 35.00, 'approved', 'v1.0',
    NOW() - INTERVAL '3 months'   -- Had a waiver 3 months ago → will be DENIED if asked again
);

-- Insert some transactions
INSERT INTO transactions (account_id, transaction_type, amount, merchant_name, description, initiated_by)
VALUES
('a1111111-0000-0000-0000-000000000001', 'purchase', 89.99, 'Amazon', 'Amazon Prime purchase', 'customer'),
('a1111111-0000-0000-0000-000000000001', 'fee', 35.00, NULL, 'Late payment fee - August 2024', 'system'),
('a2222222-0000-0000-0000-000000000002', 'purchase', 1200.00, 'Best Buy', 'Electronics purchase', 'customer'),
('a3333333-0000-0000-0000-000000000003', 'payment', 5000.00, NULL, 'Monthly payment', 'customer');

-- Grant schema for read-only reporting role (for future compliance officer access)
-- CREATE ROLE compliance_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO compliance_reader;

\echo 'Database schema initialized successfully.'
\echo 'Tables: customers, transactions, fee_waiver_history, credit_limit_history, card_replacements, agent_sessions_audit'
