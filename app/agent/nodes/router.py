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
from app.agent.services.prompts import load_prompt
from app.core.db_task_utils import read_db_task
from app.core.models import Task

logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class RouterDecision(BaseModel):
    """Classify the incoming task into the correct category and skill level."""

    task_type: Literal["coding", "bugfixing", "analyzing"] = Field(
        description="The specific type of the task."
    )
    task_skill_level: Literal["junior", "senior"] = Field(
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
        system_message = load_prompt("systemprompt_router.md", state)
        # Router only needs the original task to make routing decision
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=3)

        task = state["task"]
        human_message_content = _build_human_message_content(
            task.name, task.description, state["task_comments"], state["pr_review_message"]
        )

        base_messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=human_message_content),
        ] + filtered_messages
        current_messages = list(base_messages)

        response = await structured_llm.ainvoke(current_messages)
        logger.info("Task type: %s", response.task_type)
        logger.info("Task skill level: %s", response.task_skill_level)
        logger.info("Task reasoning: %s", response.reasoning)

        task_type = TaskType.UNKNOWN
        if response.task_type in [t.value for t in TaskType]:
            task_type = TaskType(response.task_type)

        next_step = "reject"
        if task_type == TaskType.ANALYZING:
            next_step = "analyst"
        elif task_type == TaskType.BUGFIXING:
            next_step = "bugfixer"
        elif task_type == TaskType.CODING:
            next_step = route_to_coder_or_analyst(state, response)

        return {
            "next_step": next_step,
            "task_type": response.task_type,
            "task_skill_level": response.task_skill_level,
            "task_skill_level_reasoning": response.reasoning,
            "current_node": "router",
        }

    return router_node


def route_to_coder_or_analyst(state: AgentState, response: RouterDecision) -> str:
    if state["agent_skill_level"] == "junior" and response.task_skill_level == "senior":
        return "reject"

    db_task: Task | None = read_db_task()
    if db_task and db_task.plan_state == PlanState.APPROVED:
        return "coder"
    return "analyst"


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
