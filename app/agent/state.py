"""
Defines the state structure for the LangGraph agent.

This module contains the `AgentState` TypedDict, which represents the shared
state that is passed between nodes in the agent's workflow graph. It holds
all the necessary information for the agent to function, such as message history,
task details, and internal counters.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.agent.integrations.board_provider import BoardTask


class PlanState(StrEnum):
    """Defines the states of the plan."""

    REQUESTED = "requested"
    CREATED = "created"
    UPDATED = "updated"
    APPROVED = "approved"


class TaskType(StrEnum):
    """Defines the types of tasks."""

    UNKNOWN = "unknown"
    CODING = "coding"
    BUGFIXING = "bugfixing"
    ANALYZING = "analyzing"


class TaskStateType(StrEnum):
    """Defines the states of tasks."""

    TODO = "todo"
    IN_PROGRESS = "in progress"
    IN_REVIEW = "in review"


class AgentState(TypedDict):
    """
    Represents the state of the agent graph.

    This state is passed between all nodes in the graph. Each field holds a piece
    of information that nodes can read from or write to, allowing them to
    collaborate and track progress.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    next_step: str
    task: Optional[BoardTask]
    task_skill_level: Optional[str]
    agent_stack: str  # Backend or Frontend
    retry_count: int  # Attempts: how often switched between coder and tester
    test_result: Optional[str]
    error_log: Optional[str]  # Optional: Stores the last error explicitly
    git_branch: Optional[str]
    agent_skill_level: Optional[str]
    agent_summary: Optional[list[str]]
    plan_state: Optional[PlanState]
    current_node: Optional[str]
    last_update: Optional[datetime]
