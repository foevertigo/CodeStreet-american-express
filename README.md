# AmEx End-to-End AI Servicing Agent Architecture

## Overview
This repository contains an enterprise-grade, autonomous customer servicing pipeline built for high-frequency financial operations (Fee Waivers, Credit Limit Increases, Card Replacements). The architecture strictly enforces regulatory compliance, eliminates Large Language Model (LLM) financial hallucinations, and maintains an immutable cryptographic audit trail.

## Core Architecture Stack
- **Frontend**: Next.js 16 (Turbopack), React, Web Audio API, WebAssembly (WASM) multithreading.
- **Backend**: FastAPI, Python 3.10+, Uvicorn.
- **Orchestration**: LangGraph, Llama 3.3 70B (Groq).
- **Speech-to-Text / Text-to-Speech**: Sarvam AI (saaras:v3 / bulbul:v3) with real-time ONNX Runtime WebAssembly processing (Silero VAD).
- **Vector Database (RAG)**: ChromaDB (Local HNSW cosine space) with Groq-compatible embeddings.
- **Relational Database**: PostgreSQL (Customer profiles, transaction history).
- **Event Bus / Audit Trail**: Apache Kafka (WORM compliant event sourcing).
- **State Management**: Redis (Session persistence, distributed locks).

## Key Technical Innovations

1. **Multilingual Real-Time Voice Gateway**
   Utilizes a local ONNX-based Voice Activity Detection (VAD) model executing via WebWorkers and AudioWorklets in the browser to stream continuous audio. The pipeline detects the spoken language (e.g., Hindi, Tamil, English) via Sarvam AI, propagates the language code dynamically through the LangGraph system prompt, and synthesizes the final native-language audio response with strict JSON-tooling language guards to prevent schema corruption.

2. **Retrieval-Augmented Generation (RAG) for Compliance**
   Prior to state graph execution, the backend semantically queries a localized ChromaDB instance to retrieve authoritative compliance policy documents. These rules are injected directly into the LLM context window. The LLM is strictly prompted to govern its decisions based solely on the retrieved rule set.

3. **Deterministic Tool Execution (Zero-Hallucination)**
   The LLM is constrained to intent classification, parameter extraction, and conversational synthesis. All financial calculations, eligibility checks, and database commits are executed by deterministic Python functions.

4. **Immutable Kafka Audit Pipeline**
   Every action in the system generates a discrete event pushed to Kafka topics (`agent-actions`, `compliance-decisions`, `system-errors`). This includes `COMPLIANCE_RAG_RETRIEVAL` events, which log the exact vector chunks the AI reviewed prior to making a decision, satisfying stringent regulatory provenance requirements.

5. **Human-in-the-Loop Supervisor Dashboard**
   Real-time WebSocket streaming routes high-frustration users or unauthorized requests to a dedicated Next.js `/supervisor` dashboard, providing human agents with full conversation context and semantic intent analysis for seamless takeover.

## Local Development & Setup Instructions

To execute the full pipeline locally, the underlying infrastructure must be initialized before starting the application servers.

### 1. Initialize Infrastructure Services
The project utilizes Docker Compose to orchestrate PostgreSQL, Redis, Kafka, Zookeeper, Elasticsearch, and Logstash.

```bash
# Start all infrastructure containers in detached mode
docker compose up -d
```

### 2. Seed Databases
Once the containers are healthy, initialize the PostgreSQL schemas and seed the mock customer profiles and compliance rules.

```bash
# Execute the database seed script
python scripts/seed_db.py
```

### 3. Start the Application Servers
The backend and frontend must run concurrently.

**Terminal 1 (Backend):**
```bash
# Install dependencies if not already present
pip install -r requirements.txt

# Start the FastAPI server
python -m uvicorn ai_backend.main:app --reload --port 8000
```
docker compose up -d
**Terminal 2 (Frontend):**
```bash
cd frontend

# Install Next.js dependencies
npm install

# Start the development server
npm run dev
```

### 4. Customizing Policies
To modify the compliance rules or customer profiles for distinct testing scenarios:
- **Compliance Rules**: Edit the constants defined in `ai_backend/rag/policy_documents.py`.
- **User Profiles**: Modify the initial injection dictionaries within `scripts/seed_db.py`.
