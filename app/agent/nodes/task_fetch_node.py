"""
Task fetch node.

Fetches tasks from a board system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging
from typing import Optional

from langchain_core.messages import SystemMessage

from app.agent.integrations.board_factory import create_board_provider
from app.agent.integrations.board_provider import BoardTask
from app.agent.services.tasks_services import (
    fetch_review_comments,
    fetch_task_from_state,
    move_task_to_in_progress,
)
from app.agent.state import AgentState
from app.core.models import AgentSettings, Task
from app.core.plan_services import delete_plan

logger = logging.getLogger(__name__)


def _build_system_message_content(
    task_name: str, task_description: str, comments: list
) -> str:
    """
    Build the system message content including task details and optional review comments.

    Args:
        task_name: Name of the task
        task_description: Description of the task
        comments: List of review comments (may be empty)

    Returns:
        Formatted system message content string
    """
    system_content = f"Task: {task_name}\n\nDescription:\n{task_description}"
    if comments:
        system_content += (
            "\n\n--- The Pull Request was rejected with "
            + "the following review comments: ---\n"
            + "NOTE: The task description shows the current implementation. "
            + "The comments below indicate ADDITIONAL work that needs to be done.\n"
        )
        for comment in reversed(comments):
            author = comment.author
            text = comment.text
            date = comment.date.isoformat()
            system_content += f"\n[{date}] {author}:\n{text}\n"

        logger.info("PR review message content: %s", system_content)

    return system_content


def create_task_fetch_node(agent_settings: AgentSettings, db_task: Optional[Task]):
    """Creates a task fetch node for the agent graph."""

    async def task_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first task from the board in a specified list.
        """
        logger.info("Fetching tasks from board")

        try:
            board_provider = create_board_provider(agent_settings)

            active_task_system = agent_settings.get_active_task_system()
            if not active_task_system:
                logger.warning("No active task system configured")
                return {"task": None}

            task: Optional[BoardTask] = None
            logger.info("db_task: %s", db_task)
            if db_task and db_task.task_id:
                task = await board_provider.get_task(db_task.task_id)

            comments = []
            is_todo_task: bool = True
            if task:
                if task.state_name == active_task_system.state_in_review:
                    logger.info("task is in review, wait for user action")
                    return {"task": None}

                if task.state_name == active_task_system.state_in_progress:
                    logger.info("task is in progress and add comments")
                    comments = await fetch_review_comments(
                        board_provider,
                        task.id,
                        active_task_system.state_in_progress,
                        active_task_system.state_in_review,
                    )
                    is_todo_task = False

            if is_todo_task:
                logger.info("fetch new task from todo")
                task = await fetch_task_from_state(
                    board_provider, active_task_system.state_todo
                )

            if not task:
                logger.info("There is no current task to work on.")
                return {"task": None}

            logger.info("Processing task ID: %s - %s", task.id, task.name)
            if is_todo_task:
                await move_task_to_in_progress(
                    board_provider, task.id, active_task_system.state_in_progress
                )
                delete_plan()

            system_content = _build_system_message_content(
                task.name,
                task.description,
                comments,
            )
            return {
                "task": task,
                "messages": [SystemMessage(content=system_content)],
                "task_comments": comments,
                "current_node": "task_fetch",
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching tasks: %s", e)
            return {"task_id": None}

    return task_fetch
