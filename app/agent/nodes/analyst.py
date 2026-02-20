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
from app.agent.services.summaries import (
    append_agent_summary,
    has_finish_task_call,
    record_finish_task_summary,
)
from app.agent.state import AgentState, PlanState
from app.core.plan_utils import exist_plan, get_plan

logger = logging.getLogger(__name__)

DASHBOARD_URL = "http://localhost:5000/dashboard"


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
        if state["current_node"] != "analyst":
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

                tool_calls = getattr(response, "tool_calls", [])
                if tool_calls:
                    log_agent_response("analyst", response, attempt=attempt + 1)
                    recorded, agent_summary = record_finish_task_summary(state, "analyst", response)

                    plan_content, plan_state = _get_plan_content_and_plan_state(
                        exist_plan_before_llm_call
                    )

                    if plan_content and has_finish_task_call(response):
                        agent_summary = append_agent_summary(
                            agent_summary,
                            "Dashboard",
                            f"Plan available at\n\n {DASHBOARD_URL}",
                        )
                        recorded = True

                    agent_task = state["agent_task"]
                    agent_task.plan_content = plan_content
                    agent_task.plan_state = plan_state
                    result = {
                        "agent_task": agent_task,
                        "messages": [response],
                        "current_node": "analyst",
                        "current_tool_calls": tool_calls,
                        "prompt": human_message,
                        "system_prompt": system_message,
                        "user_message": "Review the plan and approve or reject it",
                    }
                    if recorded:
                        result["agent_summary"] = agent_summary
                    return result

                logger.warning("Attempt %d: No tool calls. Escalating strategy...", attempt + 1)
                current_tool_choice = "any"
                current_messages.append(
                    HumanMessage(content="ERROR: Invalid response. You MUST call a tool.")
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


def _get_plan_content_and_plan_state(
    exist_plan_before_llm_call: bool,
) -> tuple[str | None, PlanState | None]:
    """Get plan info after LLM call."""
    exist_plan_after_llm_call = exist_plan()
    plan_content = get_plan() if exist_plan_after_llm_call else None
    plan_state = None
    if exist_plan_after_llm_call:
        plan_state = PlanState.CREATED
        if exist_plan_before_llm_call:
            plan_state = PlanState.UPDATED

    return plan_content, plan_state
