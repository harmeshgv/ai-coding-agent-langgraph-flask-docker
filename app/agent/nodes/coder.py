import logging

from agent.state import AgentState
from agent.utils import (
    filter_messages_for_llm,
    load_system_prompt,
    log_agent_response,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def build_create_branch_prompt(card_id: str | None, card_name: str | None) -> str:
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


def create_coder_node(llm, tools, agent_stack):
    sys_msg = load_system_prompt(agent_stack, "coder")

    async def coder_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 15 messages)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages = [SystemMessage(content=sys_msg)]

        # Check if the current card is already associated with a git branch (database)
        git_branch = state.get("git_branch")
        if not git_branch:
            create_card_branch_prompt = build_create_branch_prompt(
                state.get("trello_card_id"),
                state.get("trello_card_name"),
            )
            current_messages.append(HumanMessage(content=create_card_branch_prompt))

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
                        logger,
                        "coder",
                        response,
                        attempt=attempt + 1,
                    )
                    return {"messages": [response]}

                logger.warning(
                    f"Attempt {attempt + 1}: Empty response. Escalating strategy..."
                )
                current_tool_choice = "any"
                current_messages.append(
                    AIMessage(
                        content="I have analyzed the files and planned the changes. I am ready to write the code."
                    )
                )
                current_messages.append(
                    HumanMessage(
                        content="Good. STOP THINKING. Call 'write_to_file' NOW with the complete content."
                    )
                )

            except Exception as e:
                logger.error(f"Error in LLM call (Attempt {attempt + 1}): {e}")

        # Fallback
        logger.error("Agent stuck after 3 attempts. Hard exit.")
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
