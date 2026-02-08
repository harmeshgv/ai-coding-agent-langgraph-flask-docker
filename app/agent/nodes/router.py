"""
Defines the router node for the agent graph.

This node is responsible for the initial analysis of a task. It uses a
specialized LLM call to classify the user's request and decide which
specialist agent (e.g., Coder, Bugfixer, Analyst) should handle it next.
"""

import logging
from typing import Dict, Literal

from langchain_core.messages import SystemMessage, HumanMessage
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
- **Type:** Simple bug fixes (NPE, typos), text changes, change README.md, CSS adjustments, adding a simple unit test, or basic CRUD operations.
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
    skill_level: Literal["junior", "senior"] = Field(description="Must be 'junior' or 'senior'")
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

        task = state["task"]
        human_message_content = _build_human_message_content(
            task.name, task.description, state["task_comments"], state["pr_review_message"]
        )

        base_messages = [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=human_message_content),
        ] + filtered_messages
        current_messages = list(base_messages)

        response = await structured_llm.ainvoke(current_messages)
        response.skill_level = "junior"  # hack!!!
        logger.info("Task type: %s", response.type)
        logger.info("Task skill level: %s", response.skill_level)
        logger.info("Task reasoning: %s", response.reasoning)

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
            "task_type": response.type,
            "task_skill_level": response.skill_level,
            "current_node": "router",
        }

    return router_node

def _build_human_message_content(
    task_name: str,
    task_description: str,
    comments: list,
    pr_review_message: str = "",
) -> str:
    """
    Build the human message content including task details and optional review comments.

    Args:
        task_name: Name of the task
        task_description: Description of the task
        comments: List of board review comments (may be empty)
        pr_review_message: Formatted PR review feedback (may be empty)

    Returns:
        Formatted human message content string
    """
    system_content = f"Task: {task_name}\n\nDescription:\n{task_description}"

    if comments:
        system_content += (
            "\n\n--- The Pull Request was rejected with "
            + "the following review comments: ---\n"
            + "NOTE: The task description shows the current implementation. "
            + "The comments below indicate ADDITIONAL work that needs to be done.\n"
        )
        for comment in reversed(comments):
            author = comment.author
            text = comment.text
            date = comment.date.isoformat()
            system_content += f"\n[{date}] {author}:\n{text}\n"

        logger.info("Board review message content: %s", system_content)

    if pr_review_message:
        system_content += pr_review_message
        logger.info("PR review message appended: %s", pr_review_message)

    return system_content
