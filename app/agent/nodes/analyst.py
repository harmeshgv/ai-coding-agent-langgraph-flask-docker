"""
Defines the Analyst agent node for the agent graph.

The Analyst is a specialist agent responsible for analyzing code, answering
questions about the codebase, and providing explanations without making
any modifications.
"""  # pylint: disable=duplicate-code

import logging
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.services.logging import log_agent_response
from app.agent.services.message_processing import (
    filter_messages_for_llm,
    sanitize_response,
)
from app.agent.services.prompts import load_prompt
from app.agent.services.summaries import record_finish_task_summary
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_analyst_node(llm: BaseChatModel, tools, agent_stack):
    """
    Factory function that creates the Analyst agent node.

    Args:
        llm: The language model to be used by the analyst.
        tools: A list of tools available to the analyst.
        agent_stack: The technology stack (e.g., 'backend', 'frontend')
                     to load the correct system prompt.

    Returns:
        A function that represents the analyst node.
    """

    async def analyst_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 20 messages)
        # Analyst may need more context for code analysis
        system_message = load_prompt(f"systemprompt_{agent_stack}_analyst.md", state)
        human_message = load_prompt("prompt_analyst.md", state)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=20)
        current_messages: list[BaseMessage | SystemMessage | HumanMessage] = [
            SystemMessage(content=system_message),
            HumanMessage(content=human_message),
        ]
        current_messages += filtered_messages

        current_tool_choice = "auto"

        for attempt in range(3):
            try:
                chain = llm.bind_tools(tools, tool_choice=current_tool_choice)
                response = await chain.ainvoke(current_messages)
                response = sanitize_response(response)

                has_tool_calls = bool(getattr(response, "tool_calls", []))

                if has_tool_calls:
                    log_agent_response("analyst", response, attempt=attempt + 1)
                    recorded, agent_summary = record_finish_task_summary(state, "analyst", response)
                    result = {
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
