"""Service layer for dashboard functionality.

This module contains business logic for the dashboard page,
separating concerns from the route handlers.
"""

import logging
import markdown

from app.core.localdb.agent_actions_utils import read_db_agent_actions
from app.core.localdb.agent_tasks_utils import read_db_task, update_db_task
from app.core.localdb.models import AgentAction, AgentSettings, AgentTask
from app.core.taskboard.board_factory import create_board_provider
from app.web.services import settings_service

logger = logging.getLogger(__name__)

# HTTP status codes
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_INTERNAL_SERVER_ERROR = 500


class PlanReviewError(Exception):
    """Raised when plan review processing fails."""

    def __init__(self, message: str, status_code: int = HTTP_BAD_REQUEST):
        super().__init__(message)
        self.status_code = status_code


async def get_template_context() -> dict:
    """Build complete template context for dashboard page.

    Returns:
        Dictionary with all template variables.
    """
    agent_task: AgentTask | None = read_db_task()

    plan_content = ""
    plan_exists = False
    agent_actions: list[AgentAction] = []

    if agent_task:
        agent_actions = read_db_agent_actions(agent_task)
        # logger.info("current node: %s", agent_task.current_node)
        plan_content = markdown.markdown(agent_task.plan_content) if agent_task.plan_content else ""
        plan_exists = bool(agent_task.plan_content)

    return {
        "agent_task": agent_task,
        "plan_content": plan_content,
        "plan_exists": plan_exists,
        "current_node": "todo",
        "agent_actions": agent_actions,
    }


def _get_board_provider():
    """Creates and returns a board provider from the current agent settings."""
    agent_settings: AgentSettings = settings_service.get_or_create_settings()
    return create_board_provider(agent_settings)


async def add_plan_rejection_comment(task_id: str, rejection_reason: str) -> None:
    """Adds a comment to the task with the rejection reason.
    
    Raises:
        Exception: If adding the comment fails.
    """
    logger.info("Adding rejection comment to task %s", task_id)
    board_provider = _get_board_provider()
    await board_provider.add_comment(task_id, rejection_reason)


async def move_task_to_in_progress(task_id: str) -> bool:
    """Moves the task to the state in progress."""
    logger.info("Moving task %s to in progress", task_id)
    board_provider = _get_board_provider()
    await board_provider.move_task_to_named_state(
        task_id, state_name=board_provider.get_task_system().state_in_progress
    )
    return True


def _validate_plan_review_input(new_state: str | None, rejection_reason: str | None) -> str:
    """Validate and normalize plan review input.
    
    Args:
        new_state: The new plan state ('approved' or 'rejected').
        rejection_reason: Reason for rejection (required if new_state is 'rejected').
        
    Returns:
        Normalized new_state string.
        
    Raises:
        PlanReviewError: If validation fails.
    """
    # Input validation
    if not new_state or not isinstance(new_state, str):
        raise PlanReviewError("Plan state is required and must be a string.")

    new_state = new_state.strip().lower()
    if new_state not in ["approved", "rejected"]:
        raise PlanReviewError("Invalid state. Must be 'approved' or 'rejected'.")

    rejection_reason = (rejection_reason or "").strip()

    if new_state == "rejected" and not rejection_reason:
        raise PlanReviewError("A rejection reason is required.")

    return new_state


def _rollback_task_state(task_id: str, original_state: str) -> bool:
    """Attempt to rollback task state to original value.
    
    Args:
        task_id: The task ID to rollback.
        original_state: The original plan state to restore.
        
    Returns:
        True if rollback succeeded, False otherwise.
    """
    try:
        rollback_task = update_db_task(task_id, plan_state=original_state)
        if not rollback_task:
            logger.error("Failed to rollback task state for task %s", task_id)
            return False
        return True
    except (ValueError, RuntimeError, KeyError) as exc:
        logger.exception("Exception during rollback for task %s: %s", task_id, exc)
        return False


async def process_plan_review(new_state: str | None, rejection_reason: str | None) -> dict:
    """Handle plan review transitions and side-effects.
    
    Args:
        new_state: The new plan state ('approved' or 'rejected').
        rejection_reason: Reason for rejection (required if new_state is 'rejected').
        
    Returns:
        Dictionary with success message and task details.
        
    Raises:
        PlanReviewError: If validation fails or operations cannot be completed.
    """
    # Validate input
    new_state = _validate_plan_review_input(new_state, rejection_reason)
    rejection_reason = (rejection_reason or "").strip()

    task = read_db_task()
    if not task:
        raise PlanReviewError("No active task found in database.", status_code=HTTP_NOT_FOUND)

    if new_state == "rejected" and task.plan_state not in ("created", "updated"):
        raise PlanReviewError(
            "Plan can only be rejected when it is in review.", status_code=HTTP_CONFLICT
        )

    # Store original state for potential rollback
    original_plan_state = task.plan_state

    try:
        # Update task state first
        updated_task = update_db_task(task.task_id, plan_state=new_state)
        if not updated_task:
            raise PlanReviewError("Failed to update task", status_code=HTTP_INTERNAL_SERVER_ERROR)

        # Add rejection comment if needed
        if new_state == "rejected" and rejection_reason:
            try:
                await add_plan_rejection_comment(updated_task.task_id, rejection_reason)
            except Exception as exc:
                logger.exception(
                    "Failed to add rejection comment to task %s. Rolling back state change.", 
                    updated_task.task_id
                )
                # Rollback the state change
                _rollback_task_state(task.task_id, original_plan_state)
                raise PlanReviewError(
                    "Failed to add rejection comment. Plan state has been rolled back.", 
                    status_code=HTTP_INTERNAL_SERVER_ERROR
                ) from exc

        # Move task to in progress
        try:
            moved = await move_task_to_in_progress(updated_task.task_id)
        except Exception as exc:
            logger.exception(
                "Failed to move task %s to in progress. Rolling back state change.", 
                updated_task.task_id
            )
            # Rollback the state change
            _rollback_task_state(task.task_id, original_plan_state)
            raise PlanReviewError(
                "Failed to move task to in progress. Plan state has been rolled back.", 
                status_code=HTTP_INTERNAL_SERVER_ERROR
            ) from exc

        if not moved:
            raise PlanReviewError(
                "Failed to move task to in progress", status_code=HTTP_INTERNAL_SERVER_ERROR
            )

        return {
            "message": f"Plan state updated to {new_state}",
            "task_id": updated_task.task_id,
            "plan_state": updated_task.plan_state,
        }

    except PlanReviewError:
        # Re-raise our custom errors
        raise
    except Exception as exc:
        logger.exception("Unexpected error in process_plan_review")
        # Attempt rollback if we have an original state
        if 'original_plan_state' in locals():
            _rollback_task_state(task.task_id, original_plan_state)
        raise PlanReviewError(
            "An unexpected error occurred. Plan state has been rolled back.",
            status_code=HTTP_INTERNAL_SERVER_ERROR
        ) from exc
