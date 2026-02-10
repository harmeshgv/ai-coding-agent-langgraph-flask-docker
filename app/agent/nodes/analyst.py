"""
Defines the Analyst agent node for the agent graph.

The Analyst is a specialist agent responsible for analyzing code, answering
questions about the codebase, and providing explanations without making
any modifications.
"""  # pylint: disable=duplicate-code

import logging

from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.services.logging import log_agent_response
from app.agent.services.message_processing import (
    filter_messages_for_llm,
    sanitize_response,
)
from app.agent.services.prompts import load_prompt
from app.agent.services.summaries import record_finish_task_summary
from app.agent.state import AgentState, PlanState
from app.core.models import Task
from app.core.plan_utils import exist_plan, get_plan
from app.core.db_task_utils import update_db_task, read_db_task

logger = logging.getLogger(__name__)


def create_analyst_node(llm: BaseChatModel, tools):
    """
    Factory function that creates the Analyst agent node.

    Args:
        llm: The language model to be used by the analyst.
        tools: A list of tools available to the analyst.

    Returns:
        A function that represents the analyst node.
    """

    async def analyst_node(state: AgentState):  # pylint: disable=too-many-locals
        logger.info("--- ANALYST node ---")
        # Filter messages to keep only recent relevant context (original task + last 20 messages)
        # Analyst may need more context for code analysis
        system_message = load_prompt("systemprompt_analyst.md", state)
        human_message = load_prompt("prompt_analyzing.md", state)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=20)
        current_messages: list[BaseMessage | SystemMessage | HumanMessage] = [
            SystemMessage(content=system_message),
            HumanMessage(content=human_message),
        ]
        current_messages += filtered_messages

        current_tool_choice = "auto"

        exist_plan_before_llm_call = exist_plan()
        for attempt in range(3):
            try:
                chain = llm.bind_tools(tools, tool_choice=current_tool_choice)
                response = await chain.ainvoke(current_messages)
                response = sanitize_response(response)

                has_tool_calls = bool(getattr(response, "tool_calls", []))

                if has_tool_calls:
                    log_agent_response("analyst", response, attempt=attempt + 1)
                    recorded, agent_summary = record_finish_task_summary(state, "analyst", response)

                    plan, plan_state = _get_plan_info_in_db_task(exist_plan_before_llm_call)
                    _save_plan_state(plan_state)
                    result = {
                        "plan": plan,
                        "plan_state": plan_state,
                        "messages": [response],
                        "current_node": "analyst",
                        "prompt": human_message,
                        "system_prompt": system_message,
                    }
                    if recorded:
                        result["agent_summary"] = agent_summary
                    return result

                logger.warning("Attempt %d: No tool calls. Escalating strategy...", attempt + 1)
                current_tool_choice = "any"
                current_messages.append(
                    HumanMessage(
                        content="ERROR: Invalid response. You MUST call a tool. "
                        + "Use 'finish_task' to complete your analysis."
                    )
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in LLM call (Attempt %d): %s", attempt + 1, e)

        # Fallback
        logger.error("Agent stuck after 3 attempts. Hard exit.")

        fallback_message = AIMessage(
            content="Analysis stuck.",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"summary": "Analysis could not complete due to invalid responses."},
                    "id": "call_emergency",
                    "type": "tool_call",
                }
            ],
        )
        recorded, agent_summary = record_finish_task_summary(state, "analyst", fallback_message)
        result = {"messages": [fallback_message], "current_node": "analyst"}
        if recorded:
            result["agent_summary"] = agent_summary
        return result

    return analyst_node


def _get_plan_info_in_db_task(exist_plan_before_llm_call: bool) -> tuple[str, PlanState]:
    """Get plan info after LLM call."""
    exist_plan_after_llm_call = exist_plan()
    plan = get_plan() if exist_plan_after_llm_call else None
    plan_state = None
    if exist_plan_after_llm_call:
        plan_state = PlanState.CREATED
        if exist_plan_before_llm_call:
            plan_state = PlanState.UPDATED

    return plan, plan_state


def _save_plan_state(plan_state: PlanState):
    db_task: Task | None = read_db_task()
    if plan_state and db_task:
        update_db_task(db_task.task_id, plan_state=plan_state.value)
