"""
Defines the state structure for the LangGraph agent.

This module contains the `AgentState` TypedDict, which represents the shared
state that is passed between nodes in the agent's workflow graph. It holds
all the necessary information for the agent to function, such as message history,
task details, and internal counters.
"""

from enum import StrEnum
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class PlanState(StrEnum):
    """Defines the states of the plan."""

    REQUESTED = "requested"
    CREATED = "created"
    UPDATED = "updated"
    APPROVED = "approved"


class AgentState(TypedDict):
    """
    Represents the state of the agent graph.

    This state is passed between all nodes in the graph. Each field holds a piece
    of information that nodes can read from or write to, allowing them to
    collaborate and track progress.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    next_step: str
    agent_stack: str  # Backend or Frontend
    retry_count: int  # Versuche, wie oft zwischen coder und tester gewechselt wurde
    test_result: Optional[str]
    error_log: Optional[str]  # Optional: Speichert den letzten Fehler explizit
    task_id: Optional[str]
    task_name: Optional[str]
    task_state_id: Optional[str]
    git_branch: Optional[str]
    agent_skill_level: Optional[str]
    task_skill_level: Optional[str]
    agent_summary: Optional[list[str]]
    plan_state: Optional[PlanState]
