"""
orchestrator.py — LangGraph Orchestrator with RAG-augmented compliance context,
                  multilingual support, and strict tool JSON language guard.
"""

import logging
from typing import Dict, Any, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from ai_backend.config import settings
from ai_backend.agent.state import AgentState
from ai_backend.agent.prompts import SYSTEM_PROMPT
from ai_backend.agent.tools import (
    tool_waive_fee,
    tool_increase_limit,
    tool_replace_card,
    tool_set_travel_notification,
    tool_escalate_to_human
)
from audit_service.redis_client import RedisSessionClient

logger = logging.getLogger(__name__)

# Register all deterministic tools
TOOLS = [
    tool_waive_fee,
    tool_increase_limit,
    tool_replace_card,
    tool_set_travel_notification,
    tool_escalate_to_human
]

# In-memory session store fallback if Redis is unreachable
IN_MEMORY_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Sarvam language code → human-readable name
LANGUAGE_NAMES = {
    "hi-IN": "Hindi",
    "bn-IN": "Bengali",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
    "en-IN": "English",
    "en-US": "English",
}


def get_llm():
    """Initializes LLM instance using Groq API key settings."""
    if settings.groq_api_key:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                groq_api_key=settings.groq_api_key,
                model_name=settings.model_name,
                temperature=0.1
            )
        except Exception as e:
            logger.warning(f"ChatGroq initialization failed: {e}. Falling back to ChatOpenAI.")

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.groq_api_key or settings.openai_api_key,
        base_url="https://api.groq.com/openai/v1" if settings.groq_api_key else None,
        temperature=0.1
    )


def agent_node(state: AgentState) -> Dict[str, Any]:
    """
    Agent reasoning node: invoke LLM with full augmented context.
    Injects: customer profile + RAG compliance rules + transaction history + language guard.
    """
    llm = get_llm().bind_tools(TOOLS)

    messages = state.get("messages", [])
    account_id = state.get("account_id", "")
    customer_profile = state.get("customer_profile") or {}
    detected_language = state.get("detected_language") or "en-IN"
    rag_context = state.get("rag_context") or ""
    transaction_history = state.get("transaction_history") or ""

    lang_name = LANGUAGE_NAMES.get(detected_language, "English")
    cust_name = f"{customer_profile.get('first_name', '')} {customer_profile.get('last_name', '')}".strip()

    # ── Build the full augmented system prompt ────────────────────────────────
    system_text = SYSTEM_PROMPT

    # 1. Language instruction WITH the critical tool-JSON guard
    if detected_language not in ("en-IN", "en-US"):
        system_text += (
            f"\n\n## LANGUAGE INSTRUCTION\n"
            f"The customer is communicating in {lang_name} ({detected_language}).\n"
            f"You MUST respond to the customer in {lang_name}.\n"
            f"CRITICAL: If you invoke any tool, the tool name and ALL JSON argument keys "
            f"and values MUST remain strictly in English (e.g., account_id, fee_type, reason). "
            f"NEVER translate tool names or JSON arguments — only your conversational text to the customer should be in {lang_name}."
        )
    else:
        system_text += "\n\n## LANGUAGE INSTRUCTION\nRespond in clear, professional English."

    # 2. Customer profile context (always present)
    system_text += (
        f"\n\n## CURRENT CUSTOMER CONTEXT\n"
        f"- Account ID: {account_id}\n"
        f"- Name: {cust_name}\n"
        f"- Account Status: {customer_profile.get('account_status', 'unknown').upper()}\n"
        f"- Credit Score: {customer_profile.get('credit_score', 'N/A')}\n"
        f"- Annual Income: ${customer_profile.get('annual_income', 0):,.2f}\n"
        f"- Credit Limit: ${customer_profile.get('credit_limit', 0):,.2f}\n"
        f"- Current Balance: ${customer_profile.get('current_balance', 0):,.2f}"
    )

    # 3. RAG-retrieved compliance rules (semantic match to user query)
    if rag_context:
        system_text += (
            f"\n\n## RELEVANT COMPLIANCE RULES (Policy Engine — do not deviate from these)\n"
            f"{rag_context}\n"
            f"Use these exact rules when explaining decisions to the customer. "
            f"Do NOT paraphrase policy rules from memory — only use the text above."
        )

    # 4. Transaction history (if available)
    if transaction_history:
        system_text += (
            f"\n\n## CUSTOMER RECENT ACTIVITY\n"
            f"{transaction_history}"
        )

    full_messages = [SystemMessage(content=system_text)] + messages

    response = llm.invoke(full_messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """Conditional edge router: check if last message contains tool calls."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return END


def create_agent_graph():
    """Builds the LangGraph compiled state graph."""
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(TOOLS))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Global compiled graph instance
graph = create_agent_graph()


def _get_transaction_history(account_id: str) -> str:
    """
    Fetches recent account activity from Postgres (fee waivers, limit changes, card replacements).
    Returns a formatted string for injection into the system prompt.
    Gracefully returns empty string if DB is unavailable.
    """
    try:
        from audit_service.postgres_client import PostgresClient
        client = PostgresClient()

        history_parts = []

        # Fee waivers
        try:
            waivers = client.get_fee_waiver_count_last_year(account_id)
            history_parts.append(f"- Fee waivers in past 12 months: {waivers}")
        except Exception:
            pass

        return "\n".join(history_parts) if history_parts else ""
    except Exception as e:
        logger.debug(f"Transaction history lookup skipped: {e}")
        return ""


class ConversationManager:
    """
    Interface for handling multi-turn conversations with Redis session persistence
    and in-memory fallback. Now RAG-augmented and multilingual.
    """

    def __init__(self):
        try:
            self.redis_client = RedisSessionClient()
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}). Using in-memory session manager.")
            self.redis_client = None

    def _get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if self.redis_client:
            try:
                return self.redis_client.get_session(session_id)
            except Exception as e:
                logger.warning(f"Redis get_session error: {e}")
        return IN_MEMORY_SESSIONS.get(session_id)

    def _set_session(self, session_id: str, state: Dict[str, Any]):
        IN_MEMORY_SESSIONS[session_id] = state
        if self.redis_client:
            try:
                self.redis_client.set_session(session_id, state)
            except Exception as e:
                logger.warning(f"Redis set_session error: {e}")

    def process_message(
        self,
        session_id: str,
        account_id: str,
        user_message_text: str,
        channel: str = "web",
        customer_profile: Optional[Dict[str, Any]] = None,
        detected_language: Optional[str] = "en-IN",
    ) -> Dict[str, Any]:
        """
        Executes a full conversation turn:
        1. Loads session history
        2. Retrieves relevant compliance rules via RAG (+ fires Kafka audit event)
        3. Fetches transaction history from Postgres
        4. Invokes LangGraph with full augmented context
        5. Returns reply + tools executed + language_code
        """
        existing_state = self._get_session(session_id) or {}

        # Reconstruct message history from serialized session
        raw_messages = existing_state.get("messages", [])
        messages = []
        for m in raw_messages:
            if isinstance(m, dict):
                role = m.get("role")
                content = m.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
                elif role == "tool":
                    messages.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id", "")))
            elif isinstance(m, BaseMessage):
                messages.append(m)

        messages.append(HumanMessage(content=user_message_text))

        # ── Step 1: RAG — retrieve relevant compliance rules ─────────────────
        rag_context = ""
        try:
            from ai_backend.rag.compliance_rag import retrieve_relevant_rules
            rag_context = retrieve_relevant_rules(
                query=user_message_text,
                top_k=3,
                session_id=session_id,
                account_id=account_id,
            )
            if rag_context:
                logger.info(f"RAG retrieved {rag_context.count('[RULE_')} rule(s) for query: '{user_message_text[:60]}'")
        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")

        # ── Step 2: Transaction history ──────────────────────────────────────
        transaction_history = _get_transaction_history(account_id)

        # ── Step 3: Build LangGraph state ────────────────────────────────────
        state_input: AgentState = {
            "messages": messages,
            "account_id": account_id,
            "session_id": session_id,
            "channel": channel,
            "intent": existing_state.get("intent"),
            "customer_profile": customer_profile or existing_state.get("customer_profile"),
            "action_outcome": existing_state.get("action_outcome"),
            "escalated": existing_state.get("escalated", False),
            "escalation_reason": existing_state.get("escalation_reason"),
            "frustration_score": existing_state.get("frustration_score", 0.0),
            "detected_language": detected_language or existing_state.get("detected_language", "en-IN"),
            "rag_context": rag_context,
            "transaction_history": transaction_history,
        }

        final_state = graph.invoke(state_input)

        # ── Step 4: Extract reply and tool results ───────────────────────────
        final_messages = final_state.get("messages", [])
        assistant_reply = ""
        tools_executed = []

        for msg in final_messages:
            if isinstance(msg, AIMessage) and msg.content:
                assistant_reply = msg.content
            elif isinstance(msg, ToolMessage):
                tools_executed.append({
                    "name": getattr(msg, "name", "tool"),
                    "content": msg.content
                })

        # Serialize messages for session storage
        serializable_messages = []
        for msg in final_messages:
            if isinstance(msg, HumanMessage):
                serializable_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                serializable_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                serializable_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": getattr(msg, "tool_call_id", "")
                })

        save_payload = {
            "session_id": session_id,
            "account_id": account_id,
            "messages": serializable_messages,
            "customer_profile": customer_profile,
            "tools_executed": tools_executed,
            "escalated": final_state.get("escalated", False),
            "detected_language": detected_language,
        }

        self._set_session(session_id, save_payload)

        return {
            "session_id": session_id,
            "account_id": account_id,
            "reply": assistant_reply or "Your request has been processed.",
            "tools_executed": tools_executed,
            "escalated": final_state.get("escalated", False),
            "language_code": detected_language or "en-IN",
        }
