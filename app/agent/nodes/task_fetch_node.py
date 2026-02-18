"""
Task fetch node.

Fetches tasks from a board system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging

from app.core.taskboard.board_factory import create_board_provider
from app.core.taskboard.board_provider import BoardProvider, BoardTask
from app.agent.services.pull_request import (
    format_pr_review_message,
    get_latest_open_pr_for_branch,
    get_latest_pr_review_status,
)
from app.core.task_utils import (
    fetch_review_comments,
    fetch_task_from_state,
    move_task_to_state,
)
from app.agent.state import AgentState
from app.core.localdb.models import AgentSettings, Task
from app.core.localdb.db_task_utils import (
    create_db_task,
    read_db_task,
    delete_db_task,
)

logger = logging.getLogger(__name__)


def create_task_fetch_node(agent_settings: AgentSettings):
    """Creates a task fetch node for the agent graph."""
    board_provider = create_board_provider(agent_settings)

    async def task_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first task from the board in a specified list.
        """
        if state["current_node"] != "task_fetch":
            logger.info("--- TASK FETCH node ---")
        db_task: Task | None = read_db_task()

        try:
            task_id: str | None = db_task.task_id if db_task else None
            task, task_is_new = await _resolve_task(task_id, board_provider)

            if not task:
                logger.info("There is no current task to work on.")
                return {"task": None}

            comments = []
            pr_review_message = ""
            if task_is_new:
                # if the task is new and has the state "todo" then clean up the workspace
                task = await _cleanup_new_task(task, board_provider)
            else:
                # otherwise fetch revie comments from board and pr, in order
                # to give further user information
                comments = await fetch_review_comments(
                    board_provider,
                    task.id,
                    board_provider.get_task_system().state_in_progress,
                    board_provider.get_task_system().state_in_review,
                )
                pr_review_message = _fetch_pr_review_info(task.id)

            # if a new task is get from todo then initialize its fields in localdb
            plan_state = None
            task_skill_level = None
            task_skill_level_reasoning = None
            task_type = None
            if db_task and not task_is_new:
                # if the task is not new then get its data from localdb
                plan_state = db_task.plan_state
                task_skill_level = db_task.task_skill_level
                task_skill_level_reasoning = db_task.task_skill_level_reasoning
                task_type = db_task.task_type
            return {
                "task": task,
                "task_comments": comments,
                "pr_review_message": pr_review_message,
                "plan_state": plan_state,
                "task_skill_level": task_skill_level,
                "task_skill_level_reasoning": task_skill_level_reasoning,
                "task_type": task_type,
                "current_node": "task_fetch",
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching tasks: %s", e)
            return {"task": None}

    return task_fetch


async def _cleanup_new_task(task: BoardTask, board_provider: BoardProvider) -> BoardTask:
    """
    Process the task and prepare the return value.
    """
    logger.info("Processing task ID: %s - %s", task.id, task.name)
    task = await move_task_to_state(
        board_provider=board_provider,
        task=task,
        task_state_name=board_provider.get_task_system().state_in_progress,
    )
    return task


async def _resolve_task(
    task_id: str | None, board_provider: BoardProvider
) -> tuple[BoardTask | None, bool]:
    """
    Get the last task (with task_id) or create a new task.
    See specification in task_management.md.
    Returns:
        the task
        true if the task is new (from todo) otherwise false.
    """

    if task_id:
        logger.info("Fetching tasks from board: %s", task_id)

        try:
            task = await board_provider.get_task(task_id)
        except Exception:  # pylint: disable=broad-exception-caught
            task = None

        if task:
            # check if task in review or in progress
            if task.state_name == board_provider.get_task_system().state_in_review:
                logger.info("Task is in review. Wait for user action.")
                return None, False

            if task.state_name == board_provider.get_task_system().state_in_progress:
                logger.info("Task is in progress. Add review comments.")
                return task, False

            logger.info("Last task found but it is not in review or in progress.")

    # Get a new task from todo
    logger.info("Fetching new task from todo.")
    task = await fetch_task_from_state(board_provider, board_provider.get_task_system().state_todo)
    # update local db: remove the old task and insert the new task
    if task:
        if task_id:
            delete_db_task(task_id)
        create_db_task(task.id, task.name)
    return task, True


def _fetch_pr_review_info(task_id: str) -> str:
    """
    Fetch PR review info if a PR exists for the task.

    Args:
        task_id: The task ID to check

    Returns:
        Tuple of (is_approved, formatted_review_message)
        - is_approved: True if PR is approved or no PR exists
        - formatted_review_message: Formatted message for SystemMessage, empty if approved
    """
    db_task = read_db_task(task_id=task_id)
    pr_number = db_task.pr_number
    pr_url = db_task.pr_url

    if not pr_number:
        branch_name = db_task.branch_name
        if branch_name:
            pr = get_latest_open_pr_for_branch(branch_name)
            if pr:
                pr_number = pr.number
                pr_url = pr.html_url

    if not pr_number:
        logger.info("No PR found for task %s", task_id)
        return ""

    is_approved, rejection_reviews, code_comments = get_latest_pr_review_status(pr_number)

    if is_approved:
        logger.info("PR #%d for task %s is approved", pr_number, task_id)
        return ""

    logger.info(
        "PR #%d for task %s has %d rejections and %d code comments",
        pr_number,
        task_id,
        len(rejection_reviews),
        len(code_comments),
    )

    return format_pr_review_message(pr_url or "", rejection_reviews, code_comments)
