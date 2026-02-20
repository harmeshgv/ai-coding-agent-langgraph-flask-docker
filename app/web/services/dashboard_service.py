"""Service layer for dashboard functionality.

This module contains business logic for the dashboard page,
separating concerns from the route handlers.
"""

import logging
import markdown

from app.core.localdb.agent_tasks_utils import read_db_task
from app.core.localdb.models import AgentSettings
from app.core.taskboard.board_factory import create_board_provider
from app.web.services import settings_service
from app.core.localdb.agent_actions_utils import read_db_agent_actions
from app.core.localdb.models import AgentAction, AgentTask

logger = logging.getLogger(__name__)


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


async def move_task_to_in_progress(task_id: str) -> bool:
    """Moves the task to the state in progress."""
    logger.info("Moving task %s to in progress", task_id)
    agent_settings: AgentSettings = settings_service.get_or_create_settings()
    board_provider = create_board_provider(agent_settings)
    await board_provider.move_task_to_named_state(
        task_id, state_name=board_provider.get_task_system().state_in_progress
    )
    return True
