"""
Defines the state structure for the LangGraph agent.

This module contains the `AgentState` TypedDict, which represents the shared
state that is passed between nodes in the agent's workflow graph. It holds
all the necessary information for the agent to function, such as message history,
task details, and internal counters.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.core.taskboard.board_provider import BoardTask, BoardComment
from app.core.localdb.models import AgentTask


class PlanState(StrEnum):
    """Defines the states of the plan."""

    REQUESTED = "requested"
    CREATED = "created"
    UPDATED = "updated"
    APPROVED = "approved"
    REJECTED = "rejected"


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


class AgentStack(StrEnum):
    """Supported technology stacks for the agent runtime."""

    BACKEND = "backend"
    FRONTEND = "frontend"


class AgentState(TypedDict):
    """
    Represents the state of the agent graph.

    This state is passed between all nodes in the graph. Each field holds a piece
    of information that nodes can read from or write to, allowing them to
    collaborate and track progress.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    next_step: str
    board_task: BoardTask | None
    board_task_comments: list[BoardComment]
    agent_task: AgentTask | None
    pr_review_message: str | None
    agent_stack: AgentStack
    retry_count: int  # Attempts: how often switched between coder and tester
    test_result: str | None
    error_log: str | None  # Optional: Stores the last error explicitly
    git_branch: str | None
    agent_skill_level: str | None
    agent_summary: list[str] | None
    current_node: str | None
    current_tool_calls: list[dict]
    last_update: datetime | None
    prompt: str | None
    system_prompt: str | None
    tech_stack: str | None
