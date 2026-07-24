"""
orchestrator.py — LangGraph Orchestrator & State Machine (with Resilient In-Memory Fallback)
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


def get_llm():
    """
    Initializes LLM instance using Groq or OpenAI API key settings.
    """
    if settings.groq_api_key:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                groq_api_key=settings.groq_api_key,
                model_name=settings.model_name,
                temperature=0.1
            )
        except Exception as e:
            logger.warning(f"ChatGroq initialization failed: {e}. Falling back to ChatOpenAI with Groq base URL.")
    
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.groq_api_key or settings.openai_api_key,
        base_url="https://api.groq.com/openai/v1" if settings.groq_api_key else None,
        temperature=0.1
    )


def agent_node(state: AgentState) -> Dict[str, Any]:
    """
    Agent reasoning node: invoke LLM with system prompt and message history.
    """
    llm = get_llm().bind_tools(TOOLS)
    
    messages = state.get("messages", [])
    account_id = state.get("account_id", "")
    customer_profile = state.get("customer_profile") or {}
    
    cust_name = f"{customer_profile.get('first_name', '')} {customer_profile.get('last_name', '')}".strip()
    system_text = (
        SYSTEM_PROMPT +
        f"\n\nCURRENT CUSTOMER CONTEXT:\n"
        f"- Account ID: {account_id}\n"
        f"- Name: {cust_name}\n"
        f"- Credit Score: {customer_profile.get('credit_score')}\n"
        f"- Annual Income: ${customer_profile.get('annual_income', 0):,.2f}\n"
        f"- Credit Limit: ${customer_profile.get('credit_limit', 0):,.2f}"
    )
    
    full_messages = [SystemMessage(content=system_text)] + messages
    
    response = llm.invoke(full_messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """
    Conditional edge router: check if last message contains tool calls.
    """
    messages = state.get("messages", [])
    if not messages:
        return END
    
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return END


def create_agent_graph():
    """
    Builds the LangGraph compiled state graph.
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(TOOLS))
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


# Global compiled graph instance
graph = create_agent_graph()


class ConversationManager:
    """
    Interface for handling multi-turn conversations with Redis session persistence (with in-memory fallback).
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
        customer_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a conversation turn for a session.
        """
        existing_state = self._get_session(session_id) or {}
        
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
            "frustration_score": existing_state.get("frustration_score", 0.0)
        }

        final_state = graph.invoke(state_input)
        
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
            "escalated": final_state.get("escalated", False)
        }
        
        self._set_session(session_id, save_payload)

        return {
            "session_id": session_id,
            "account_id": account_id,
            "reply": assistant_reply or "Your request has been processed.",
            "tools_executed": tools_executed,
            "escalated": final_state.get("escalated", False)
        }
