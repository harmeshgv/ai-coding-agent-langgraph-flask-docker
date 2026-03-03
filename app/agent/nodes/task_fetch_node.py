"""
Task fetch node.

Fetches tasks from a task system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging

from app.core.taskprovider.task_factory import create_task_provider
from app.core.taskprovider.task_provider import TaskProvider, ProviderTask
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
from app.core.localdb.models import AgentSettings, AgentTask
from app.core.localdb.agent_tasks_utils import (
    create_db_task,
    read_db_task,
    delete_db_task,
)

logger = logging.getLogger(__name__)


def create_task_fetch_node(agent_settings: AgentSettings):
    """Creates a task fetch node for the agent graph."""
    task_provider = create_task_provider(agent_settings)

    async def task_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first task from the task system in a specified list.
        """
        if state["current_node"] != "task_fetch":
            logger.info("--- TASK FETCH node ---")

        try:
            provider_task, agent_task, task_is_new = await _resolve_task(
                state["agent_task"], task_provider
            )

            if not provider_task:
                logger.info("There is no current task to work on.")
                return {"provider_task": None}

            comments = []
            pr_review_message = ""
            if task_is_new:
                # if the task is new and has the state "todo" then clean up the workspace
                provider_task = await _cleanup_new_task(provider_task, task_provider)
            else:
                # otherwise fetch revie comments from task system and pr, in order
                # to give further user information
                comments = await fetch_review_comments(
                    task_provider,
                    provider_task.id,
                    task_provider.get_task_system().state_in_progress,
                    task_provider.get_task_system().state_in_review,
                )
                pr_review_message = _fetch_pr_review_info(provider_task.id)

            return {
                "provider_task": provider_task,
                "provider_task_comments": comments,
                "pr_review_message": pr_review_message,
                "agent_task": agent_task,
                "current_node": "task_fetch",
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching tasks: %s", e)
            return {"provider_task": None}

    return task_fetch


async def _cleanup_new_task(task: ProviderTask, task_provider: TaskProvider) -> ProviderTask:
    """
    Process the task and prepare the return value.
    """
    logger.info("Processing task ID: %s - %s", task.id, task.name)
    task = await move_task_to_state(
        task_provider=task_provider,
        task=task,
        task_state_name=task_provider.get_task_system().state_in_progress,
    )
    return task


async def _resolve_task(
    agent_task: AgentTask | None, task_provider: TaskProvider
) -> tuple[ProviderTask | None, AgentTask | None, bool]:
    """
    Get the last task (with task_id) or create a new task.
    See specification in task_management.md.
    Returns:
        the task
        true if the task is new (from todo) otherwise false.
    """

    if agent_task:
        logger.info("Fetching tasks from task system: %s", agent_task.task_id)

        try:
            provider_task = await task_provider.get_task(agent_task.task_id)
        except Exception:  # pylint: disable=broad-exception-caught
            provider_task = None

        if provider_task:
            # check if task in review or in progress
            if provider_task.state_name == task_provider.get_task_system().state_in_review:
                logger.info("Task is in review. Wait for user action.")
                return None, agent_task, False

            if provider_task.state_name == task_provider.get_task_system().state_in_progress:
                logger.info("Task is in progress. Add review comments.")
                return provider_task, agent_task, False

            logger.info("Last task found but it is not in review or in progress.")

    # Get a new task from todo
    logger.info("Fetching new task from todo.")
    provider_task = await fetch_task_from_state(
        task_provider, task_provider.get_task_system().state_todo
    )
    # update local db: remove the old task and insert the new task
    if provider_task:
        if agent_task:
            delete_db_task(agent_task.task_id)
        agent_task = create_db_task(provider_task.id, provider_task.name)
    return provider_task, agent_task, True


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
