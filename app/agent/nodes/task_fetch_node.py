"""
Task fetch node.

Fetches tasks from a board system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging
from datetime import datetime

from langchain_core.messages import SystemMessage

from app.agent.integrations.board_factory import create_board_provider
from app.agent.integrations.board_provider import (  # pylint: disable=unused-import
    BoardProvider,
    BoardTask,
)
from app.agent.services.pull_request import (
    check_pr_exists_for_branch,
    format_pr_review_message,
    get_latest_open_pr_for_branch,
    get_latest_pr_review_status,
)
from app.agent.state import AgentState
from app.core.models import AgentSettings
from app.core.task_repository import (
    get_branch_for_task,
    get_pr_info_for_task,
    remove_task_from_db,
)

logger = logging.getLogger(__name__)


async def _get_task_context(
    board_provider: BoardProvider, agent_settings: AgentSettings
):
    active_task_system = agent_settings.get_active_task_system()
    if not active_task_system:
        logger.warning("No active task system configured")
        return None

    incoming_state_name = active_task_system.readfrom_state
    if not incoming_state_name:
        logger.warning("task_readfrom_state not configured")
        return None

    in_progress_state_name = active_task_system.in_progress_state

    task_context = None
    if in_progress_state_name:
        task_context = await fetch_task_from_state(
            board_provider, in_progress_state_name
        )

    if not task_context:
        task_context = await fetch_task_from_state(board_provider, incoming_state_name)
    return task_context


async def _ensure_task_in_progress(
    board_provider: BoardProvider,
    task_context: dict,
    task_id: str,
    task_in_progress_state_name: str | None,
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
        board_provider, task_id, readfrom_state_id, task_in_progress_state_name
    )
    task_context["state_id"] = move_task_result["state_id"]
    return task_context


async def _fetch_review_comments(
    board_provider: BoardProvider,
    task_id: str,
    original_state_name: str,
    task_in_progress_state_name: str,
    review_state_name: str,
) -> list:
    """
    Fetch comments from review if task was returned from review to in-progress.

    Args:
        board_provider: BoardProvider
        task_id: id of task
        original_state_name: name of state before task was moved to in-progress
        task_in_progress_state_name: name of in-progress state
        review_state_name: name of review state

    Returns:
        List of comments if task was in review and returned, empty list otherwise.
    """
    comments = []
    # if task was in review and returned to in-progress,
    # fetch comments between review and move to in-progress
    if original_state_name == task_in_progress_state_name:
        all_comments = await board_provider.get_comments(task_id)

        if board_provider.get_type() == "github":
            # For GitHub, only return last comment if a PR exists for the branch
            branch_name = get_branch_for_task(task_id)
            if branch_name and check_pr_exists_for_branch(branch_name):
                return all_comments[-1:] if all_comments else []
            return []

        latest_move = await get_latest_move_to_in_progress(
            board_provider, task_id, review_state_name, task_in_progress_state_name
        )
        logger.info("Latest move: %s", latest_move)
        if latest_move:
            comments = filter_comments_between_timestamps(
                all_comments,
                latest_move["review_timestamp"],
                latest_move["return_timestamp"],
            )
            logger.info("Found move from review to in-progress")
        else:
            logger.info("No move from review to in-progress found")
    else:
        logger.info("Original state is not in progress")

    if comments:
        logger.info("Found comments to append")
    else:
        logger.info("No comments to append")

    return comments


def _fetch_pr_review_info(task_id: str) -> tuple[bool, str]:
    """
    Fetch PR review info if a PR exists for the task.

    Args:
        task_id: The task ID to check

    Returns:
        Tuple of (is_approved, formatted_review_message)
        - is_approved: True if PR is approved or no PR exists
        - formatted_review_message: Formatted message for SystemMessage, empty if approved
    """
    pr_number, pr_url = get_pr_info_for_task(task_id)

    if not pr_number:
        branch_name = get_branch_for_task(task_id)
        if branch_name:
            pr = get_latest_open_pr_for_branch(branch_name)
            if pr:
                pr_number = pr.number
                pr_url = pr.html_url

    if not pr_number:
        logger.info("No PR found for task %s", task_id)
        return True, ""

    is_approved, rejection_reviews, code_comments = get_latest_pr_review_status(
        pr_number
    )

    if is_approved:
        logger.info("PR #%d for task %s is approved", pr_number, task_id)
        return True, ""

    logger.info(
        "PR #%d for task %s has %d rejections and %d code comments",
        pr_number,
        task_id,
        len(rejection_reviews),
        len(code_comments),
    )

    return False, format_pr_review_message(pr_url or "", rejection_reviews, code_comments)


def _build_system_message_content(
    task_name: str,
    task_description: str,
    comments: list,
    pr_review_message: str = "",
) -> str:
    """
    Build the system message content including task details and optional review comments.

    Args:
        task_name: Name of the task
        task_description: Description of the task
        comments: List of board review comments (may be empty)
        pr_review_message: Formatted PR review feedback (may be empty)

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

        logger.info("Board review message content: %s", system_content)

    if pr_review_message:
        system_content += pr_review_message
        logger.info("PR review message appended")

    return system_content


def create_task_fetch_node(agent_settings: AgentSettings):
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
                return {"task_id": None}

            review_state_name = active_task_system.moveto_state
            if not review_state_name:
                return {"task_id": None}

            task_in_progress_state_name = active_task_system.in_progress_state

            task_context = await _get_task_context(board_provider, agent_settings)
            if not task_context:
                return {"task_id": None}

            task = task_context["task"]
            original_state_name = task_context["state_name"]

            task_context = await _ensure_task_in_progress(
                board_provider,
                task_context,
                task.id,
                task_in_progress_state_name,
            )

            comments = await _fetch_review_comments(
                board_provider,
                task.id,
                original_state_name,
                task_in_progress_state_name,
                review_state_name,
            )

            _, pr_review_message = _fetch_pr_review_info(task.id)

            logger.info("Processing task ID: %s - %s", task.id, task.name)

            system_content = _build_system_message_content(
                task.name,
                task.description,
                comments,
                pr_review_message,
            )

            return {
                "task_id": task.id,
                "task_name": task.name,
                "task_state_id": task_context["state_id"],
                "task_description": task.description,
                "messages": [SystemMessage(content=system_content)],
                "task_comments": comments,
                "current_node": "task_fetch",
            }
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching tasks: %s", e)
            return {"task_id": None}

    return task_fetch


async def fetch_task_from_state(
    board_provider: BoardProvider, state_name: str
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
            "Moving task %s to in-progress state: %s",
            task_id,
            task_in_progress_state_name,
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


async def get_latest_move_to_in_progress(
    board_provider: BoardProvider,
    task_id: str,
    review_state_name: str,
    in_progress_state_name: str,
) -> dict | None:
    """Returns timestamps if the latest move was from review to in-progress.

    Returns:
        dict with 'review_timestamp' and 'return_timestamp' if the latest move
        was from review to in-progress, None otherwise.
    """
    try:
        state_moves = await board_provider.get_state_moves(task_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to fetch state moves for task %s: %s.",
            task_id,
            e,
        )
        return None

    if not state_moves:
        return None

    # Process moves chronologically to determine review/in-progress transitions
    sorted_moves = sorted(state_moves, key=lambda move: move.date)

    # Find moves from review_state to in_progress_state
    # Each move has state_before and state_after
    review_to_progress_moves = []
    for idx, move in enumerate(sorted_moves):
        if (
            move.state_before == review_state_name
            and move.state_after == in_progress_state_name
        ):
            # Find when the task entered the review state
            # Look backwards for the previous move that resulted in the review state
            review_timestamp = None
            for prev_move in reversed(sorted_moves[:idx]):
                if prev_move.state_after == review_state_name:
                    review_timestamp = prev_move.date
                    break

            # If we can't find when it entered review, skip this move
            if review_timestamp:
                review_to_progress_moves.append(
                    {
                        "review_timestamp": review_timestamp,  # When it entered review
                        "return_timestamp": move.date,  # When it moved back to in-progress
                    }
                )

    if not review_to_progress_moves:
        logger.info(
            "Task %s has no moves from '%s' to '%s'.",
            task_id,
            review_state_name,
            in_progress_state_name,
        )
        return None

    # Get the latest such move (most recent return to in-progress from review)
    latest_move = max(review_to_progress_moves, key=lambda x: x["return_timestamp"])
    logger.info(
        "Task %s last moved from '%s' to '%s' at %s (review was at %s).",
        task_id,
        review_state_name,
        in_progress_state_name,
        latest_move["return_timestamp"].isoformat(),
        latest_move["review_timestamp"].isoformat(),
    )
    return latest_move


def filter_comments_between_timestamps(
    comments: list, start: datetime, end: datetime
) -> list:
    """Filters comments between two timestamps (inclusive)."""
    filtered_comments = []
    for comment in comments:
        if start <= comment.date <= end:
            filtered_comments.append(comment)
    return filtered_comments
