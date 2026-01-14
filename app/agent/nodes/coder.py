"""
Defines the Coder agent node for the agent graph.

The Coder is a specialist agent responsible for writing new code, creating
files, and implementing features based on the task requirements.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agent.state import AgentState
from agent.utils import (
    filter_messages_for_llm,
    load_system_prompt,
    log_agent_response,
    record_finish_task_summary,
)

logger = logging.getLogger(__name__)


def create_coder_node(llm, tools, agent_stack):
    """
    Factory function that creates the Coder agent node.

    Args:
        llm: The language model to be used by the coder.
        tools: A list of tools available to the coder.
        agent_stack: The technology stack to load the correct system prompt.

    Returns:
        A function that represents the coder node.
    """
    sys_msg = load_system_prompt(agent_stack, "coder")

    async def coder_node(state: AgentState):
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
                        "coder",
                        response,
                        attempt=attempt + 1,
                    )
                    recorded, agent_summary = record_finish_task_summary(
                        state,
                        "coder",
                        response,
                    )
                    result = {"messages": [response]}
                    if recorded:
                        result["agent_summary"] = agent_summary
                    return result

                logger.warning(
                    "Attempt %d: Empty response. Escalating strategy...", attempt + 1
                )
                current_tool_choice = "any"
                current_messages.append(
                    AIMessage(
                        content="I have analyzed the files and planned the changes. "
                        + "I am ready to write the code."
                    )
                )
                current_messages.append(
                    HumanMessage(
                        content="Good. STOP THINKING. Call 'write_to_file' "
                        + "NOW with the complete content."
                    )
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in LLM call (Attempt %d): %s", attempt + 1, e)
        # Fallback
        logger.error("Agent stuck after 3 attempts. Hard exit.")

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
        recorded, agent_summary = record_finish_task_summary(state, "coder", fallback_message)
        result: dict[str, Any] = {"messages": [fallback_message]}
        if recorded:
            result["agent_summary"] = agent_summary
        return result

    return coder_node
