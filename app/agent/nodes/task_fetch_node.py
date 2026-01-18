"""
Task fetch node.

Fetches tasks from a board system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging
from datetime import datetime

from langchain_core.messages import SystemMessage

from app.core.task_repository import remove_task_from_db
from app.agent.integrations.board_factory import create_board_provider
from app.agent.integrations.board_provider import BoardProvider, BoardTask  # pylint: disable=unused-import
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def _get_task_context(board_provider: BoardProvider, sys_config: dict):
    incoming_state_name = sys_config["task_readfrom_state"]
    in_progress_state_name = sys_config.get("task_in_progress_state")

    task_context = None
    if in_progress_state_name:
        task_context = await fetch_task_from_state(
            board_provider, in_progress_state_name, sys_config
        )

    if not task_context:
        task_context = await fetch_task_from_state(
            board_provider, incoming_state_name, sys_config
        )
    return task_context


async def _ensure_task_in_progress(
    board_provider: BoardProvider,
    task_context: dict,
    task_id: str,
    task_in_progress_state_name: str | None,
    sys_config: dict,
) -> dict:
    """
    Moves the task to the in-progress state if needed, updating the task_context.
    """
    if not task_in_progress_state_name:
        return task_context

    current_state_name = task_context["state_name"]
    if current_state_name == task_in_progress_state_name:
        return task_context

    remove_task_from_db(task_id)
    readfrom_state_id = task_context["state_id"]
    move_task_result = await move_task_to_in_progress(
        board_provider, task_id, readfrom_state_id, task_in_progress_state_name, sys_config
    )
    task_context["state_id"] = move_task_result["state_id"]
    return task_context


def create_task_fetch_node(sys_config: dict):
    """Creates a task fetch node for the agent graph."""

    async def task_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first task from the board in a specified list.
        """
        logger.info("Fetching tasks from board")

        try:
            board_provider = create_board_provider(sys_config)

            review_state_name = sys_config.get("task_moveto_state")
            if not review_state_name:
                return {"task_id": None}

            task_in_progress_state_name = sys_config.get("task_in_progress_state")

            task_context = await _get_task_context(board_provider, sys_config)
            if not task_context:
                return {"task_id": None}

            task = task_context["task"]

            task_context = await _ensure_task_in_progress(
                board_provider,
                task_context,
                task.id,
                task_in_progress_state_name,
                sys_config,
            )

            comments = await board_provider.get_comments(task.id)

            review_timestamp = await get_review_transition_timestamp(
                board_provider, task.id, review_state_name
            )
            if review_timestamp:
                comments = filter_comments_after_timestamp(comments, review_timestamp)

            content = task.name + "\n" + task.description
            if comments:
                content += (
                    "\n\n--- The Pull Request was rejected with "
                    + "the following comments: ---\n"
                )
                for comment in reversed(comments):
                    author = comment.author
                    text = comment.text
                    date = comment.date.isoformat()
                    content += f"\n[{date}] {author}:\n{text}\n"

            logger.info("Processing task ID: %s - %s", task.id, task.name)            

            # Build SystemMessage with full context including rejection comments if present
            system_content = f"Task: {task.name}\n\nDescription:\n{task.description}"
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

            return {
                "task_id": task.id,
                "task_name": task.name,
                "task_state_id": task_context["state_id"],
                "task_description": task.description,
                "messages": [
                    SystemMessage(content=system_content)
                ],
                "task_comments": comments,
            }
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching tasks: %s", e)
            return {"task_id": None}

    return task_fetch


async def fetch_task_from_state(
    board_provider: BoardProvider, state_name: str, sys_config: dict  # pylint: disable=unused-argument
) -> dict | None:
    """Fetch a task from a board state."""
    board_states = await board_provider.get_states()
    target_state = next(
        (data for data in board_states if data["name"] == state_name),
        None,
    )

    if not target_state:
        logger.warning("%s state not found", state_name)
        return None

    state_id = target_state["id"]
    logger.info("Found %s state id: %s", state_name, state_id)

    tasks = await board_provider.get_tasks_from_state(state_id)
    if not tasks:
        logger.info("No open tasks found in %s.", state_name)
        return None

    task = tasks[0]

    return {
        "task": task,
        "state_id": state_id,
        "state_name": state_name,
    }


async def move_task_to_in_progress(
    board_provider: BoardProvider,
    task_id: str,
    current_state_id: str,
    task_in_progress_state_name: str,
    sys_config: dict,  # pylint: disable=unused-argument
) -> dict:
    """
    Moves the task to the in-progress state before task processing begins.
    """
    if not task_in_progress_state_name:
        logger.warning(
            "task_in_progress_state not configured, skipping move to in-progress state"
        )
    else:
        logger.info(
            "Moving task %s to in-progress state: %s", task_id, task_in_progress_state_name
        )

        try:
            progress_state_id = await board_provider.move_task_to_named_state(
                task_id, task_in_progress_state_name
            )
            return {
                "state_id": progress_state_id,
            }
        except ValueError as e:
            logger.warning("Failed to move task to in-progress state: %s", e)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to move task to in-progress state: %s", e)

    return {"state_id": current_state_id}


async def get_review_transition_timestamp(
    board_provider: BoardProvider, task_id: str, review_state_name: str
) -> datetime | None:
    """Returns the timestamp of the last transition of a task to a review state."""
    try:
        state_moves = await board_provider.get_state_moves(task_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to fetch state moves for task %s: %s. Including all comments.",
            task_id,
            e,
        )
        return None

    review_timestamps = [
        move.date
        for move in state_moves
        if move.state_after == review_state_name
    ]
    if not review_timestamps:
        return None

    latest_review = max(review_timestamps)
    logger.info(
        "Task %s last moved to '%s' at %s.",
        task_id,
        review_state_name,
        latest_review.isoformat(),
    )
    return latest_review


def filter_comments_after_timestamp(
    comments: list, cutoff: datetime
) -> list:
    """Filters comments after a given timestamp."""
    filtered_comments = []
    for comment in comments:
        if comment.date >= cutoff:
            filtered_comments.append(comment)
    return filtered_comments
