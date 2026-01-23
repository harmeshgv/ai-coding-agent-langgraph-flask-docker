"""
Defines the router node for the agent graph.

This node is responsible for the initial analysis of a task. It uses a
specialized LLM call to classify the user's request and decide which
specialist agent (e.g., Coder, Bugfixer, Analyst) should handle it next.
"""

import logging
from typing import Dict, Literal

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from app.agent.services.message_processing import filter_messages_for_llm
from app.agent.state import AgentState, PlanState, TaskType

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You are the Senior Technical Lead.
Your job is to analyze the incoming task and classify its type and its skill level to assign
it to the correct developer profile.

# CLASSIFICATION TYPES

## 1. 'coding': For implementing new features, creating new files, or refactoring.

## 2. 'bugfixing': For fixing errors, debugging, or solving issues in existing code.

## 3. 'analyzing': For explaining code, reviewing architecture, or answering questions (NO code changes).

# CLASSIFICATION SKILL LEVELS

## 1. Junior Developer Level
Assign 'junior' if the task meets these criteria:
- **Scope:** Isolated to a single file or method.
- **Type:** Simple bug fixes (NPE, typos), text changes, CSS adjustments, adding a simple unit test, or basic CRUD operations.
- **Ambiguity:** The instructions are explicit and step-by-step.
- **Risk:** Low risk of breaking the overall system architecture.
- **Dependencies:** No new libraries or complex dependency management required.

## 2. Senior Developer Level
Assign 'senior' if the task meets these criteria:
- **Scope:** Affects multiple modules, requires architectural changes, or cross-cutting concerns (logging, security, transaction management).
- **Type:** Refactoring, performance optimization, concurrency/threading, database schema migrations, or integrating external 3rd-party APIs.
- **Ambiguity:** The task is vague (e.g., "Improve performance") and requires investigation or design decisions.
- **Risk:** High risk of regression or side effects.
- **Knowledge:** Requires deep understanding of frameworks (e.g., Spring Boot internals, React Lifecycle nuances).

# INPUT FORMAT
You will receive a `TASK_TITLE` and a `TASK_DESCRIPTION`.

# OUTPUT FORMAT
You must return a valid JSON object with exactly two fields:
1.  type: The result string, which must be exactly "coding", "bugfixing" or "analyzing"
2. `skill_level`: The result string, which must be exactly "junior" or "senior".
3. `reasoning`: A short sentence explaining why you chose the category.

# EXAMPLES

**Input:**
Title: "Fix typo in Login Button"
Description: "The button says 'Logni' instead of 'Login'."
**Output:**
{
  "type": "bugfixing",
  "skill_level": "junior",
  "reasoning": "Simple text change in UI, isolated scope."
}

**Input:**
Title: "Implement JWT Authentication"
Description: "Secure all API endpoints using JWT tokens and add role-based access control."
**Output:**
{
  "type": "coding",
  "skill_level": "senior",
  "reasoning": "Involves security, architectural changes across multiple endpoints, and understanding of auth flows."
}

**Input:**
Title: "Add age validation"
Description: "User age must be > 18 in the registration service."
**Output:**
{
  "type": "coding",
  "skill_level": "junior",
  "reasoning": "Basic logic check in a single service method."
}"""


# pylint: disable=too-few-public-methods
class RouterDecision(BaseModel):
    """Classify the incoming task into the correct category and skill level."""

    type: Literal["coding", "bugfixing", "analyzing"] = Field(
        description="The specific type of the task."
    )
    skill_level: Literal["junior", "senior"] = Field(
        description="Must be 'junior' or 'senior'"
    )
    reasoning: str = Field(description="Why this classification was chosen")


def create_router_node(llm):
    """
    Factory function that creates the router node for the agent graph.

    Args:
        llm: The language model to be used for routing decisions.

    Returns:
        A function that represents the router node.
    """
    structured_llm = llm.with_structured_output(RouterDecision, method="json_mode")

    async def router_node(state: AgentState) -> Dict[str, str]:
        # Router only needs the original task to make routing decision
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=3)
        base_messages = [SystemMessage(content=ROUTER_SYSTEM)] + filtered_messages
        current_messages = list(base_messages)

        response = await structured_llm.ainvoke(current_messages)
        logger.info("Task type: %s", response.type)
        logger.info("Task skill level: %s", response.skill_level)

        task_type = TaskType.UNKNOWN
        if response.type in [t.value for t in TaskType]:
            task_type = TaskType(response.type)

        next_step = "analyst"
        if task_type == TaskType.BUGFIXING:
            next_step = "bugfixer"
        elif task_type == TaskType.CODING:
            if response.skill_level == "junior":
                next_step = "coder"
            #  from hiere: task_skill_level is senior
            elif state["agent_skill_level"] == "junior":
                next_step = "reject"
            # from here: agent_skill_level is senior
            elif state["plan_state"] == PlanState.APPROVED:
                next_step = "coder"

        return {
            "next_step": next_step,
            "task_type": task_type,
            "task_skill_level": response.skill_level,
            "current_node": "router",
        }

    return router_node
