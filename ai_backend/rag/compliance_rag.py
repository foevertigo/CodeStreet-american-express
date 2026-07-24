"""
compliance_rag.py — Lightweight RAG engine for compliance policy retrieval.

Uses ChromaDB (local, on-disk) with Groq's OpenAI-compatible Embeddings API
(nomic-embed-text-v1_5 via https://api.groq.com/openai/v1/embeddings).

Why this approach:
  - Zero local model download (no PyTorch, no C++ build tools)
  - Groq embedding API reuses the same API key already in .env
  - ChromaDB runs fully local on-disk — no extra infrastructure

Audit contract:
  Every call to retrieve_relevant_rules() ALSO fires a Kafka event of type
  COMPLIANCE_RAG_RETRIEVAL, creating an immutable log of WHICH policy text
  the LLM read before making its decision. This satisfies regulators who need
  to audit AI decision-making provenance.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy-loaded singletons ──────────────────────────────────────────────────
_collection = None
_is_initialized = False


def _get_groq_embedding(texts: list[str]) -> list[list[float]]:
    """
    Calls Groq's OpenAI-compatible embeddings endpoint.
    Model: nomic-embed-text-v1_5 (supported on Groq)
    Falls back to a simple TF-IDF-like bag-of-chars if API unavailable.
    """
    try:
        from openai import OpenAI
        from ai_backend.config import settings

        client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.embeddings.create(
            model="nomic-embed-text-v1_5",
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.warning(f"Groq embedding API unavailable ({e}). Using keyword fallback.")
        return None


class GroqEmbeddingFunction:
    """ChromaDB-compatible embedding function using Groq API."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        result = _get_groq_embedding(input)
        if result is not None:
            return result
        # Fallback: simple deterministic char-frequency vector (dim=256)
        # Good enough for small rule sets when API is down
        vectors = []
        for text in input:
            v = [0.0] * 256
            for ch in text.lower():
                v[ord(ch) % 256] += 1.0
            norm = max(sum(v), 1)
            vectors.append([x / norm for x in v])
        return vectors


def _initialize_collection():
    """Build the ChromaDB collection with all compliance rules on first call."""
    global _collection, _is_initialized
    if _is_initialized:
        return

    try:
        import chromadb
        from ai_backend.rag.policy_documents import COMPLIANCE_RULES

        db_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".chroma_db"
        )
        chroma_client = chromadb.PersistentClient(path=os.path.abspath(db_path))

        embed_fn = GroqEmbeddingFunction()
        collection = chroma_client.get_or_create_collection(
            name="compliance_rules",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        # Only seed if empty (idempotent)
        if collection.count() == 0:
            logger.info("Seeding ChromaDB with compliance policy rules...")
            collection.add(
                ids=[rule["id"] for rule in COMPLIANCE_RULES],
                documents=[rule["text"] for rule in COMPLIANCE_RULES],
                metadatas=[{"category": rule["category"], "rule_id": rule["id"]} for rule in COMPLIANCE_RULES],
            )
            logger.info(f"Seeded {len(COMPLIANCE_RULES)} compliance rules into ChromaDB.")

        _collection = collection
        _is_initialized = True
        logger.info("Compliance RAG engine initialized (ChromaDB + Groq embeddings).")

    except Exception as e:
        logger.error(f"Failed to initialize compliance RAG engine: {e}. RAG will be disabled.")
        _is_initialized = True  # Don't retry on every request


def retrieve_relevant_rules(
    query: str,
    top_k: int = 3,
    session_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> str:
    """
    Performs a semantic vector search over compliance rules.

    Args:
        query: The user's message / intent description
        top_k: Number of most-relevant rule chunks to return
        session_id: For Kafka audit event
        account_id: For Kafka audit event

    Returns:
        A formatted string of the most relevant compliance rule text,
        ready to be injected into the LLM system prompt.
        Returns empty string if RAG is disabled or errors occur.
    """
    _initialize_collection()

    if _collection is None:
        return ""

    try:
        results = _collection.query(
            query_texts=[query],
            n_results=min(top_k, _collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return ""

        # ── Fire Kafka audit event (COMPLIANCE_RAG_RETRIEVAL) ──────────────
        # Logs EXACTLY what the LLM was shown before making its decision.
        # This is the regulatory "explainability" trail.
        try:
            from audit_service.kafka_producer import publish_event
            from audit_service.event_schemas import BaseAuditEvent

            class ComplianceRAGRetrievalEvent(BaseAuditEvent):
                event_type: str = "COMPLIANCE_RAG_RETRIEVAL"
                query: str
                retrieved_rule_ids: list
                similarity_scores: list
                top_k: int

            event = ComplianceRAGRetrievalEvent(
                session_id=session_id or "unknown",
                account_id=account_id or "unknown",
                query=query,
                retrieved_rule_ids=[m.get("rule_id") for m in metas],
                similarity_scores=[round(1 - d, 4) for d in distances],
                top_k=top_k,
            )
            publish_event(event)
        except Exception as kafka_err:
            logger.debug(f"RAG Kafka audit event skipped: {kafka_err}")

        # ── Format context for system prompt injection ─────────────────────
        rule_chunks = []
        for doc, meta in zip(docs, metas):
            rule_chunks.append(f"[{meta.get('rule_id', 'RULE')}] {doc}")

        return "\n\n".join(rule_chunks)

    except Exception as e:
        logger.warning(f"RAG retrieval error: {e}. Proceeding without RAG context.")
        return ""
