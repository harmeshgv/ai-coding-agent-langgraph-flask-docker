"""Service functions to process task"""

import logging
from datetime import datetime
from typing import Optional


from app.core.taskboard.board_provider import (  # pylint: disable=unused-import
    BoardProvider,
    BoardTask,
)
from app.agent.services.pull_request import check_pr_exists_for_branch
from app.core.localdb.db_task_utils import read_db_task

logger = logging.getLogger(__name__)


async def fetch_task_from_state(board_provider: BoardProvider, state_name: str) -> BoardTask | None:
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

    return tasks[0]


async def move_task_to_state(
    board_provider: BoardProvider,
    task: BoardTask,
    task_state_name: str,
) -> BoardTask:
    """
    Moves the task to the in-progress state before task processing begins.
    """
    modified_task: Optional[BoardTask] = task
    if not task_state_name:
        logger.warning("task_in_progress_state not configured, skipping move to in-progress state")
    else:
        logger.info(
            "Moving task %s to in-progress state: %s",
            task.id,
            task_state_name,
        )

        try:
            await board_provider.move_task_to_named_state(task.id, task_state_name)
            modified_task = await board_provider.get_task(task.id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to move task to in-progress state: %s", e)

    match modified_task:
        case BoardTask():
            return modified_task
        case None:
            raise RuntimeError("modified_task is none")


async def fetch_review_comments(
    board_provider: BoardProvider,
    task_id: str,
    in_progress_state_name: str,
    in_review_state_name: str,
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
    all_comments = await board_provider.get_comments(task_id)

    if board_provider.get_type() == "github":
        # For GitHub, only return last comment if a PR exists for the branch
        db_task = read_db_task(task_id=task_id)
        branch_name = db_task.branch_name
        if branch_name and check_pr_exists_for_branch(branch_name):
            return all_comments[-1:] if all_comments else []
        return []

    latest_move = await get_latest_move_to_in_progress(
        board_provider, task_id, in_review_state_name, in_progress_state_name
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

    if comments:
        logger.info("Found comments to append")
        for comment in comments:
            logger.info("comment: %s", comment.text)
    else:
        logger.info("No comments to append")

    return comments


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
        if move.state_before == review_state_name and move.state_after == in_progress_state_name:
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


def filter_comments_between_timestamps(comments: list, start: datetime, end: datetime) -> list:
    """Filters comments between two timestamps (inclusive)."""
    filtered_comments = []
    for comment in comments:
        if start <= comment.date <= end:
            filtered_comments.append(comment)
    return filtered_comments
