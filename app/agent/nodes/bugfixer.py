"""
Defines the Bugfixer agent node for the agent graph.

The Bugfixer is a specialist agent responsible for debugging code, analyzing
errors, and implementing fixes for identified issues.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agent.services.logging import log_agent_response
from agent.services.message_processing import filter_messages_for_llm
from agent.services.prompts import load_system_prompt
from agent.services.summaries import record_finish_task_summary
from agent.state import AgentState

logger = logging.getLogger(__name__)


def create_bugfixer_node(llm, tools, agent_stack):
    """
    Factory function that creates the Bugfixer agent node.

    Args:
        llm: The language model to be used by the bugfixer.
        tools: A list of tools available to the bugfixer.
        agent_stack: The technology stack (e.g., 'backend', 'frontend')
                     to load the correct system prompt.

    Returns:
        A function that represents the bugfixer node.
    """
    sys_msg = load_system_prompt(agent_stack, "bugfixer")

    async def bugfixer_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 15 messages)
        # pylint: disable=duplicate-code
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages: list[BaseMessage | SystemMessage] = [
            SystemMessage(content=sys_msg)
        ]
        current_messages += filtered_messages

        current_tool_choice = "auto"

        for attempt in range(3):
            try:
                chain = llm.bind_tools(tools, tool_choice=current_tool_choice)
                response = await chain.ainvoke(current_messages)

                has_content = bool(response.content)
                has_tool_calls = bool(getattr(response, "tool_calls", []))

                if has_content or has_tool_calls:
                    log_agent_response(
                        "bugfixer",
                        response,
                        attempt=attempt + 1,
                    )
                    recorded, agent_summary = record_finish_task_summary(
                        state,
                        "bugfixer",
                        response,
                    )
                    result = {"messages": [response]}
                    if recorded:
                        result["agent_summary"] = agent_summary
                    return result

                logger.warning("Attempt %d: Empty response. Escalating...", attempt + 1)
                current_tool_choice = "any"
                current_messages.append(AIMessage(content="Thinking..."))
                current_messages.append(
                    HumanMessage(content="ERROR: Empty response. Use a tool!")
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in LLM call (Attempt %d): %s", attempt + 1, e)

        # Fallback
        fallback_message = AIMessage(
            content="Stuck.",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"summary": "Agent stuck."},
                    "id": "call_emergency",
                    "type": "tool_call",
                }
            ],
        )
        recorded, agent_summary = record_finish_task_summary(
            state,
            "bugfixer",
            fallback_message,
        )
        result: dict[str, Any] = {"messages": [fallback_message]}
        if recorded:
            result["agent_summary"] = agent_summary
        return result

    return bugfixer_node
