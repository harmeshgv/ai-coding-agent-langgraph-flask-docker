"""
Defines the router node for the agent graph.

This node is responsible for the initial analysis of a task. It uses a
specialized LLM call to classify the user's request and decide which
specialist agent (e.g., Coder, Bugfixer, Analyst) should handle it next.
"""

import logging
from typing import Dict, Literal

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from pydantic import BaseModel, Field

from app.agent.services.message_processing import filter_messages_for_llm
from app.agent.state import AgentState, PlanState, TaskType
from app.agent.services.prompts import load_prompt
from app.core.localdb.db_task_utils import read_db_task
from app.core.localdb.models import Task

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
        logger.info("--- ROUTER node ---")
        system_message = load_prompt("systemprompt_router.md", state)
        human_message = load_prompt("prompt_routing.md", state)
        # Router only needs the original task to make routing decision
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=3)
        current_messages: list[BaseMessage | SystemMessage | HumanMessage] = [
            SystemMessage(content=system_message),
            HumanMessage(content=human_message),
        ]
        current_messages += filtered_messages

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
            db_task: Task | None = read_db_task()
            plan_state = db_task.plan_state if db_task else None
            next_step = route_to_coder_or_analyst(
                plan_state, state["agent_skill_level"], response.task_skill_level
            )

        return {
            "next_step": next_step,
            "task_type": response.task_type,
            "task_skill_level": response.task_skill_level,
            "task_skill_level_reasoning": response.reasoning,
            "current_node": "router",
        }

    return router_node


def route_to_coder_or_analyst(
    plan_state: PlanState, agent_skill_level: str, task_skill_level: str
) -> str:
    """Route the task to coder or analyst."""
    if plan_state == PlanState.APPROVED:
        logger.info("Plan is approved, routing to coder")
        return "coder"

    # if the difficulty of the task is higher than the agent's skill level, reject it
    if agent_skill_level == "junior" and task_skill_level == "senior":
        logger.info("Task difficulty is higher than agent skill level, rejecting")
        return "reject"

    # if the difficulty of the task is lower to the agent's skill level,
    # and the task can be executed by the coder without a plan, then route to coder
    if agent_skill_level == "senior" and task_skill_level == "junior":
        logger.info("Task difficulty is lower than agent skill level, routing to coder")
        return "coder"

    # if the difficulty of the task is equal to the agent's skill level,
    # and the task must be planned by the analyst, then route to analyst
    logger.info("Task difficulty is equal to agent skill level, routing to analyst")
    return "analyst"
