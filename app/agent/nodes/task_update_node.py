"""
Defines the task update node for the agent graph.

This node is responsible for finalizing a task on the board. It adds a summary
comment to the task and moves it to a "done" or "completed" list,
based on the agent's configuration.
"""

import logging
from time import sleep
from typing import Optional

from langchain_core.messages import AIMessage, ToolMessage

from app.core.taskboard.board_factory import create_board_provider
from app.core.taskboard.board_provider import BoardProvider, BoardTask
from app.agent.services.summaries import get_agent_summary_entries
from app.agent.state import AgentState
from app.core.localdb.models import AgentSettings

AGENT_DEFAULT_COMMENT = "Task completed by AI Agent."

logger = logging.getLogger(__name__)


def create_task_update_node(agent_settings: AgentSettings):
    """
    Factory function that creates the task update node.

    Args:
        agent_settings: Agent configuration containing board provider credentials
            and settings.

    Returns:
        A function that represents the task update node.
    """

    async def task_update(state: AgentState) -> dict:
        """
        Updates the task with a comment and moves it to the specified list.
        """
        if state["current_node"] != "task_update":
            logger.info("--- TASK UPDATE node ---")
        board_task: BoardTask | None = state["board_task"]
        if not board_task:
            logger.warning("No task found in state")
            return {}

        logger.info("Updating task in board %s", board_task)

        board_provider: BoardProvider = create_board_provider(agent_settings)

        try:
            final_comments = _build_agent_comments(state)
            for comment in final_comments:
                await board_provider.add_comment(board_task.id, comment)
                sleep(0.1)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to add comment to task: %s", e)

        try:
            task_moveto_state = board_provider.get_task_system().state_in_review
            if not task_moveto_state:
                logger.warning("state_in_review not configured for provider %s", board_provider)
                return

            task_moveto_state_id = await board_provider.move_task_to_named_state(
                task_id=board_task.id, state_name=task_moveto_state
            )

            return {
                "task_state_id": task_moveto_state_id,
                "current_node": "task_update",
            }
        except ValueError as exc:
            logger.warning(str(exc))
            return
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error moving task to state: %s", e)
            return

    return task_update


def get_agent_result(messages):
    """
    Searches backward in the history for the 'finish_task' Tool-Call.
    The summary or result of the tool call is returned.
    If not found, returns the default comment.
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call["name"] == "finish_task":
                    return tool_call["args"].get("summary", AGENT_DEFAULT_COMMENT)

    return AGENT_DEFAULT_COMMENT


def _check_for_task_creation(state: AgentState) -> tuple[bool, str | None]:
    """
    Checks if create_task was called and returns task info.

    Returns:
        Tuple of (was_task_created, task_info_message)
    """
    messages = state.get("messages", [])

    for i, msg in enumerate(messages):
        if not isinstance(msg, AIMessage) or not msg.tool_calls:
            continue

        for tool_call in msg.tool_calls:
            if tool_call["name"] != "create_task":
                continue

            if i + 1 >= len(messages) or not isinstance(messages[i + 1], ToolMessage):
                continue

            tool_response = messages[i + 1].content
            if (
                isinstance(tool_response, str)
                and "Successfully created implementation task" in tool_response
            ):
                return True, tool_response

    return False, None


def _build_agent_comments(state: AgentState) -> list[str]:
    """
    Builds a list of agent comments from the agent summary entries.
    If a new task was created, adds a second comment about the task creation.
    """
    entries = get_agent_summary_entries(state)
    if not entries:
        summary_list = [AGENT_DEFAULT_COMMENT]
    else:
        summary_list = []
        for entry in entries:
            summary_list.append(f"**Agent Update:**\n\n {entry}")

    task_created, task_info = _check_for_task_creation(state)

    if task_created and task_info:
        summary_list.append(f"**New Implementation Task Created:**\n\n{task_info}")

    return summary_list
