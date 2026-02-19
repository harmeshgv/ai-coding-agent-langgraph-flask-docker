"""Tool for adding comments to tasks."""

import logging

from langchain.tools import ToolRuntime, tool

from app.core.localdb.models import AgentSettings
from app.core.taskboard.board_factory import create_board_provider

logger = logging.getLogger(__name__)


@tool
async def add_task_comment(
    comment: str,
    runtime: ToolRuntime[AgentSettings, dict],
) -> str:
    """
    Adds a comment to the current task in the board system.

    Args:
        comment: The comment text to add to the task.
        runtime: The runtime context containing the current AgentSettings.
    Returns:
        Confirmation message with the comment details.
    """
    try:
        # Extract the current task from AgentState
        current_task = runtime.state.get("board_task")
        if not current_task:
            return "Error: No current task found in state"

        task_id = current_task.id
        task_name = current_task.name

        # Create board provider and add comment
        agent_settings = runtime.context
        if not agent_settings:
            return "Error: No agent settings found in runtime context"

        board_provider = create_board_provider(agent_settings)
        await board_provider.add_comment(task_id, comment)

        logger.info(
            "Added comment to task '%s' (%s): %s",
            task_name,
            task_id,
            comment[:100] + "..." if len(comment) > 100 else comment,
        )

        return (
            f"Successfully added comment to task '{task_name}' (ID: {task_id})\nComment: {comment}"
        )

    except ValueError as e:
        logger.error("Failed to add comment: %s", str(e))
        return f"Error: {str(e)}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Board provider error: %s", str(e))
        return f"Failed to add comment: {str(e)}"
