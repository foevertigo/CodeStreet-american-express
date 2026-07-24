#  AmEx End-to-End AI Servicing Agent — FinTech at Scale

**Component owner:** AI Servicing Team  
**Stack:** Next.js · FastAPI · LangGraph · Python · Llama 3.3 (Groq) · PostgreSQL · Redis · Kafka · Elasticsearch

This repository contains the complete **End-to-End Autonomous Customer Servicing & Audit Pipeline**, built for the FinTech at Scale hackathon. It automates high-frequency customer requests (Fee Reversals, Credit Limit Increases, Card Replacements) using an LLM orchestrator while maintaining strict regulatory compliance, zero financial hallucinations, and a complete immutable audit trail.

---

##  Key Innovations 

1. **Zero-Hallucination Guarantee**: The LLM (LangGraph + Llama 3) only handles intent classification and entity extraction. **All financial calculations, eligibility checks, and DB updates are executed by deterministic Python policy functions.** The LLM never decides if a fee is waived or a limit is increased.
2. **Interactive Persona Switcher**: Test 5 distinct demo customer profiles (e.g., eligible, ineligible, suspended) to verify deterministic policy enforcement live.
3. **Voice Gateway Simulator**: Built-in toggle to simulate a voice call center interaction (like Twilio / AWS Connect) complete with Web Speech API TTS readout.
4. **Human-in-the-Loop Supervisor**: Real-time `/supervisor` dashboard via WebSockets. Features live conversation replay, sentiment/frustration analysis, and a one-click manual takeover console.
5. **Immutable Audit & Compliance Explorer**: A `/audit` dashboard streaming live Kafka events with cryptographic WORM proofs to satisfy compliance officers.

---

## Architecture Overview

```text
+---------------------------------------------------------------------------------------------------+
|                                        EXTERNAL INTERFACES                                        |
|  +--------------------------------+  +-------------------------------+  +----------------------+  |
|  | Web/Mobile Channel (Next.js)   |  | Voice Gateway Simulator       |  | Smartphone Chat App  |  |
|  +----------------+---------------+  +---------------+---------------+  +----------+-----------+  |
+-------------------|----------------------------------|-----------------------------|--------------+
                    |                                  |                             |
                    +----------------------------------v-----------------------------+
                                                       |
                                           +-----------v-----------+
                                           | API Gateway / Auth    |
                                           | Manager (JWT/Account) |
                                           +-----------+-----------+
                                                       |
+------------------------------------------------------v--------------------------------------------+
|                                      BACKEND SERVICES CLUSTER                                     |
|                                                                                                   |
|  +------------------------------+   +------------------------------+   +-----------------------+  |
|  |     AI AGENT CLUSTER         |   | DETERMINISTIC POLICY ENGINE  |   | INTEGRATION SERVICES  |  |
|  |  (LangGraph / FastAPI)       |   |  - Compliance Rules          |   |  - Core Banking API   |  |
|  |  - Orchestrator (State)      |==>|  - Credit Policies           |==>|  - CRM System         |  |
|  |  - LLM (Groq/GPT-4/Claude)   |   |  - Fraud Detection           |   |  - Card Management    |  |
|  |  - Prompt Registry           |   +--------------+---------------+   +-----------+-----------+  |
|  +--------------+---------------+                  |                               |              |
+-----------------|----------------------------------|-------------------------------|--------------+
                  |                                  |                               |
       +----------v----------+            +----------v----------+             +------v------+
       |  REDIS SESSION DB   |            |  POSTGRES CUSTOMER  |             | KAFKA AUDIT |
       | (LangGraph State)   |            |  & TRANSACTION DB   |             |  EVENT BUS  |
       +---------------------+            +---------------------+             +------+------+
                                                                                     |
                                                                              +------v------+
                                                                              | ELASTICSEARCH|
                                                                              | AUDIT WORM  |
                                                                              +------+------+
                                                                                     |
                                                                       +-------------v--------------+
                                                                       |   HUMAN-IN-THE-LOOP        |
                                                                       |   SUPERVISOR DASHBOARD     |
                                                                       |   (Real-time Takeover & WS)|
                                                                       +----------------------------+
```

---

##  Quick Start

### 1. Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- (Optional) **Docker Desktop** for running the local Postgres/Redis/Kafka/Elasticsearch cluster

### 2. Configure Environment
```bash
# Copy the example env file
copy .env.example .env

# Add your LLM provider API key to .env (Default is Groq Llama-3)
# GROQ_API_KEY=gsk_your_key_here
```

*(Note: The system is designed to gracefully fall back to in-memory/mock storage for DBs and Event Buses if Docker infrastructure is not running, allowing you to instantly run the AI agent.)*

### 3. Start Backend (FastAPI + LangGraph)
```bash
# Create venv and install dependencies
python -m venv .venv
.venv\Scripts\activate          # On Windows
pip install -r requirements.txt

# Start backend server
uvicorn ai_backend.main:app --host 0.0.0.0 --port 8000 --reload
```
API runs on `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

### 4. Start Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```
App runs on `http://localhost:3000`.

---

##  Testing the Agent End-to-End

Navigate to `http://localhost:3000` to access the main Customer Servicing UI.

**Test Personas (Selectable via UI dropdown):**
| Name | Credit Score | Hackathon Test Scenario |
|---|---|---|
| **James Wilson** | 750 | Fee waiver INELIGIBLE (already used 1 waiver in past 12 months) |
| **Sarah Chen** | 620 | Fee waiver eligible, Credit Limit Increase INELIGIBLE (<700 score) |
| **Marcus Johnson**| 810 | Eligible for ALL policies (Try requesting a $50k CLI) |
| **Emily Rodriguez**| 580 | New account |
| **David Kim** | 490 | Suspended account |

**Try these prompts:**
- "Can you please waive my $35 late fee?"
- "I want to request a credit limit increase to $50,000. My annual income is $250,000."
- "I lost my card in New York! Please freeze it and send a replacement."
- "I am unsatisfied. Transfer me to a human supervisor." (Check the `/supervisor` tab!)
- "I am traveling to Tokyo from Aug 1 to Aug 15."

---

##  Project Structure

```text
CodeStreet-american-express/
├── ai_backend/                 # Core AI & Policy Engine
│   ├── agent/
│   │   ├── orchestrator.py     # LangGraph workflow & Redis session manager
│   │   ├── tools.py            # Deterministic Policy Engine Tools
│   │   ├── state.py            # Agent state schema
│   │   └── prompts.py          # System Persona & Guardrails
│   ├── auth.py                 # Customer auth & mock DB
│   ├── config.py               # Settings (API keys, endpoints)
│   └── main.py                 # FastAPI endpoints & WebSockets
├── frontend/                   # Next.js Application
│   ├── app/
│   │   ├── page.tsx            # Main Customer Servicing Chat
│   │   ├── supervisor/         # Human Supervisor Command Center
│   │   └── audit/              # Kafka Immutable Audit Explorer
├── audit_service/              # Shared data infrastructure package
├── .env                        # Local configs (Keys, DB connections)
└── docker-compose.yml          # Full infra stack (Postgres, Redis, Kafka, ES)
```

---

##  Contributing

We welcome contributions! As we prepare for the final Hackathon judging, please adhere to the following workflow:

1. **Create an Issue/Feature Request**: Describe what you intend to build.
2. **Branch Naming**: `feature/your-feature-name` or `bugfix/issue-description`
3. **AI Policy Rules**: Any new policy logic MUST be added to `ai_backend/agent/tools.py`. The LLM should never calculate risk or authorize transactions directly.
4. **Audit Trail**: Every new tool must emit a `ComplianceDecisionEvent` via the `safe_publish_event` helper.
5. **Code Style**: We use `black` for Python and `eslint`/`prettier` for Next.js.
6. **Pull Requests**: Ensure all backend tests pass (`pytest tests/`) and include a summary of your changes.

---

##  Infrastructure Reference (Docker)

To run the complete production-grade data stack (instead of the graceful fallbacks):

```bash
docker compose up -d
python scripts/seed_db.py
python scripts/verify_pipeline.py
```

- **PostgreSQL**: `localhost:5432` (Customer profiles)
- **Redis**: `localhost:6379` (LangGraph session memory)
- **Kafka**: `localhost:9092` (Topics: `agent-actions`, `compliance-decisions`, `escalations`)
- **Elasticsearch/Kibana**: `localhost:9200` / `localhost:5601` (Audit Logs)

---
*Built for the 2026 CodeStreet FinTech Hackathon.*
