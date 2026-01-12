"""
Defines the Bugfixer agent node for the agent graph.

The Bugfixer is a specialist agent responsible for debugging code, analyzing
errors, and implementing fixes for identified issues.
"""

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agent.state import AgentState
from agent.utils import (
    filter_messages_for_llm,
    load_system_prompt,
    log_agent_response,
)

logger = logging.getLogger(__name__)


def build_create_branch_prompt(card_id: str | None, card_name: str | None) -> str:
    """Constructs a dynamic prompt instructing the agent to create a git branch."""
    lines = ["No git branch is currently set for this Trello card."]
    if card_name:
        lines.append(f"- card_name: {card_name}")
    if card_id:
        lines.append(f"- card_id: {card_id}")
    lines.append(
        "Call git_create_branch(branch_name, card_id, card_name) with the values above "
        "to create and switch to a dedicated branch before coding."
    )
    return "\n".join(lines)


def build_branch_already_set_prompt(branch_name: str) -> str:
    """Constructs guidance when a git branch is already assigned to the card."""
    return (
        f"Git branch '{branch_name}' is already associated with this Trello card. "
        "Continue working on this branch and do NOT call git_create_branch."
    )


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
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages: list[BaseMessage | SystemMessage] = [
            SystemMessage(content=sys_msg)
        ]

        # Check if the current card is already associated with a git branch (database)
        git_branch = state.get("git_branch")
        if not git_branch:
            create_card_branch_prompt = build_create_branch_prompt(
                state.get("trello_card_id"),
                state.get("trello_card_name"),
            )
            current_messages.append(HumanMessage(content=create_card_branch_prompt))
        else:
            current_messages.append(
                HumanMessage(content=build_branch_already_set_prompt(git_branch))
            )

        current_messages += filtered_messages

        current_tool_choice = "auto"

        # pylint: disable=duplicate-code
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
                    return {"messages": [response]}

                logger.warning("Attempt %d: Empty response. Escalating...", attempt + 1)
                current_tool_choice = "any"
                current_messages.append(AIMessage(content="Thinking..."))
                current_messages.append(
                    HumanMessage(content="ERROR: Empty response. Use a tool!")
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in LLM call (Attempt %d): %s", attempt + 1, e)

        # Fallback
        # pylint: disable=duplicate-code
        return {
            "messages": [
                AIMessage(
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
            ]
        }

    return bugfixer_node
