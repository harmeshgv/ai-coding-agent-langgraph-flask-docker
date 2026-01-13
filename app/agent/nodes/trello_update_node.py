"""
Defines the Trello update node for the agent graph.

This node is responsible for finalizing a task in Trello. It adds a summary
comment to the Trello card and moves it to a "done" or "completed" list,
based on the agent's configuration.
"""

import logging

from langchain_core.messages import AIMessage

from agent.state import AgentState
from agent.trello_client import (
    add_comment_to_trello_card,
    move_trello_card_to_named_list,
)
from agent.utils import build_agent_summary_markdown

AGENT_DEFAULT_COMMENT = "Task completed by AI Agent."

logger = logging.getLogger(__name__)


def get_agent_result(messages):
    """
    Searches backward in the history for the 'finish_task' Tool-Call.
    The summary or result of the tool call is returned.
    If not found, returns the default comment.
    """
    for msg in reversed(messages):
        # Wir suchen nach einer AI-Nachricht, die Tools benutzt hat
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                # Prüfen, ob es das Abschluss-Tool ist
                if tool_call["name"] == "finish_task":
                    # Das Argument 'summary' oder 'result' extrahieren
                    return tool_call["args"].get("summary", AGENT_DEFAULT_COMMENT)

    return AGENT_DEFAULT_COMMENT


def _build_final_agent_comment(state: AgentState) -> str:
    """
    Prefer the aggregated agent summary, fallback to the last finish_task summary.
    """
    summary_markdown = build_agent_summary_markdown(
        state,
        heading="**Agent Update:**",
        bullet_prefix="- ",
        line_separator="\n",
    )
    if summary_markdown:
        logger.info("Using aggregated agent summary: %s", summary_markdown)
        return summary_markdown

    logger.info("Using last finish_task summary")
    latest_summary = get_agent_result(state["messages"])
    return f"**Agent Update:**\n\n- {latest_summary}"


def create_trello_update_node(sys_config: dict):
    """
    Factory function that creates the Trello update node.

    Args:
        sys_config: A dictionary containing the system configuration,
                    including Trello API credentials and board/list details.

    Returns:
        A function that represents the Trello update node.
    """

    async def trello_update(state: AgentState) -> dict:
        """
        Updates the Trello card with a comment and moves it to the specified list.
        """
        card_id = state.get("trello_card_id")
        if not card_id:
            logger.warning("No Trello card ID found in state")
            return {}

        logger.info(
            "Updating Trello card %s on board id: %s",
            card_id,
            sys_config["trello_board_id"],
        )

        # add comment to card
        try:
            final_comment = _build_final_agent_comment(state)
            await add_comment_to_trello_card(card_id, final_comment, sys_config)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to add comment to Trello card: %s", e)

        # move card to list
        try:
            trello_moveto_list = sys_config["trello_moveto_list"]
            trello_moveto_list_id = await move_trello_card_to_named_list(
                card_id, trello_moveto_list, sys_config
            )

            return {
                "trello_list_id": trello_moveto_list_id,
            }
        except ValueError as exc:
            logger.warning(str(exc))
            return {"trello_card_id": None}
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error moving card to list: %s", e)
            return {"trello_card_id": None}

    return trello_update
