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

from app.core.taskprovider.task_provider import ProviderTask, ProviderTaskComment
from app.core.localdb.models import AgentTask
from app.agent.models import AgentSummary


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

    @classmethod
    def from_string(cls, value: str) -> "TaskType":
        """Convert a string to a TaskType, normalizing whitespace and case."""
        normalized = value.strip().lower() if value else ""
        try:
            return cls(normalized)
        except ValueError:
            return cls.UNKNOWN


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
    # information from the external task system
    provider_task: ProviderTask | None
    provider_task_comments: list[ProviderTaskComment]
    # information from the table agent_tasks of the local database
    agent_task: AgentTask | None
    # agent information from settings
    agent_stack: AgentStack
    tech_stack: dict | None
    agent_skill_level: str | None
    agent_summary: list[AgentSummary] | None
    retry_count: int  # Attempts: how often switched between coder and tester
    test_result: str | None
    error_log: str | None  # Optional: Stores the last error explicitly
    # information from the git system
    git_branch: str | None
    pr_review_message: str | None
    # the last agent node that is executed
    current_node: str | None
    # the tool calls that was created from the last agent node
    current_tool_calls: list[dict]
    # the human message that was sent from the last agent node
    prompt: str | None
    # the system prompt that was sent from the last agent node
    system_prompt: str | None
    # message from the system to the user
    user_message: str | None
    last_update: datetime | None
