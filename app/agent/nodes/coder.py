"""
Defines the Coder agent node for the agent graph.

The Coder is a specialist agent responsible for writing new code, creating
files, and implementing features based on the task requirements.
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
                        "coder",
                        response,
                        attempt=attempt + 1,
                    )
                    return {"messages": [response]}

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

    return coder_node
