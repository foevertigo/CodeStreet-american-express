# AmEx AI Agent — Async Audit Pipeline & Databases

**Component owner:** Audit Pipeline Team  
**Stack:** Apache Kafka · Logstash · Elasticsearch · Redis · PostgreSQL · Python

This repository contains the **data infrastructure layer** of the FinTech AI Servicing Agent:
1. **Redis** — LangGraph conversation state store (session memory)
2. **PostgreSQL** — Customer profiles, transactions, compliance history
3. **Async Audit Pipeline** — Kafka → Logstash → Elasticsearch (WORM immutable audit trail)

---

## Architecture Overview

```
                    ┌──────────────────────────────────────────────┐
                    │  Other microservices                          │
                    │  (LangGraph, Policy Engine, Auth, Banking)   │
                    └─────────────────┬────────────────────────────┘
                                      │  from audit_service import ...
                    ┌─────────────────▼────────────────────────────┐
                    │          audit_service/ (Python Package)      │
                    │   kafka_producer · redis_client · pg_client  │
                    └──────┬─────────────┬──────────────┬──────────┘
                           │             │              │
              ┌────────────▼──┐   ┌──────▼─────┐  ┌───▼──────────┐
              │  Apache Kafka │   │   Redis    │  │  PostgreSQL  │
              │  (Event Bus)  │   │  (State)   │  │  (Customers) │
              └──────┬────────┘   └────────────┘  └──────────────┘
                     │
              ┌──────▼────────┐
              │   Logstash    │
              │ (ETL bridge)  │
              └──────┬────────┘
                     │
              ┌──────▼────────┐     ┌────────────────┐
              │ Elasticsearch │────►│ Kibana (UI)    │
              │ (Audit Trail) │     │ :5601          │
              └───────────────┘     └────────────────┘
```

---

## Quick Start

### 1. Prerequisites
- **Docker Desktop** installed and running
- **Python 3.11+**

### 2. Start Infrastructure
```bash
# Clone / navigate to project
cd "C:\Projects\american express"

# Copy environment file
copy .env.example .env

# Start all 8 Docker services
docker compose up -d

# Verify all services are up (wait ~60 seconds first)
docker compose ps
```

### 3. Install Python Dependencies
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 4. Seed the Database
```bash
python scripts/seed_db.py
```

### 5. Verify the Pipeline Works
```bash
python scripts/verify_pipeline.py
```

Expected output:
```
✅ Redis: Write/Read/Delete OK
✅ PostgreSQL: Schema OK, found customer: James Wilson
✅ Elasticsearch: Cluster status: yellow
✅ Kafka: Published 6 test events
⏳ Waiting 20s for Logstash to process...
✅ Elasticsearch ingestion: All 6/6 events found in indices
✅ PIPELINE IS FULLY OPERATIONAL
```

### 6. Open Kibana Dashboard
Visit [http://localhost:5601](http://localhost:5601) → Discover → Index pattern: `amex-audit-*`

---

## Project Structure

```
american express/
├── docker-compose.yml          # All 8 infrastructure services
├── .env                        # Environment variables (not in git)
├── .env.example                # Template for developers
├── requirements.txt            # Python dependencies
│
├── audit_service/              # Python package (other services import this)
│   ├── config.py               # Pydantic settings from .env
│   ├── event_schemas.py        # Pydantic models for all Kafka events
│   ├── kafka_producer.py       # publish_event() function
│   ├── redis_client.py         # RedisSessionClient class
│   └── postgres_client.py      # PostgresClient class
│
├── db/
│   ├── postgres/init.sql       # Full schema (auto-runs on first Docker start)
│   └── redis/redis.conf        # Redis config (password, memory, persistence)
│
├── pipeline/
│   └── logstash/
│       ├── logstash.conf       # Kafka input → Elasticsearch output pipeline
│       └── pipelines.yml       # Logstash pipeline registration
│
├── scripts/
│   ├── seed_db.py              # Insert demo customers & history
│   └── verify_pipeline.py      # End-to-end health check
│
├── tests/
│   ├── test_kafka_producer.py  # Unit tests (no Docker needed)
│   ├── test_redis_client.py
│   └── test_postgres_client.py
│
└── docs/
    └── INTEGRATION_GUIDE.md    # How other teams use this package
```

---

## Running Tests

Unit tests run without Docker (fully mocked):

```bash
pytest tests/ -v
```

---

## Kafka Topics

| Topic | Published By | Consumed By |
|---|---|---|
| `agent-actions` | LangGraph Orchestrator | Logstash → Elasticsearch |
| `compliance-decisions` | Policy Engine | Logstash → Elasticsearch |
| `card-events` | LangGraph Orchestrator | Logstash → Elasticsearch |
| `system-errors` | All services | Logstash → Elasticsearch + Alerting |
| `escalations` | LangGraph Orchestrator | Logstash → Elasticsearch + Human Dashboard |

---

## Demo Customers (Postgres)

| Name | Credit Score | Scenario |
|---|---|---|
| James Wilson | 750 | Fee waiver INELIGIBLE (used 3 months ago) |
| Sarah Chen | 620 | Fee waiver eligible, CLI ineligible |
| Marcus Johnson | 810 | Eligible for everything |
| Emily Rodriguez | 580 | New account (Feb 2024) |
| David Kim | 490 | Suspended account |

---

## Stopping Services

```bash
docker compose down          # Stop (keep data)
docker compose down -v       # Stop + delete all data (CAUTION)
```

---

## For Developers

See [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md) for:
- Copy-paste code for every event type
- Redis session state schema
- PostgreSQL query examples
- Troubleshooting guide
