"""
state.py — LangGraph Agent State Definition
"""

from typing import TypedDict, Annotated, Optional, Any, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State maintained during a conversation session in LangGraph.
    """
    messages: Annotated[List[BaseMessage], add_messages]
    account_id: str
    session_id: str
    channel: str
    intent: Optional[str]
    customer_profile: Optional[dict[str, Any]]
    action_outcome: Optional[dict[str, Any]]
    escalated: bool
    escalation_reason: Optional[str]
    frustration_score: float
