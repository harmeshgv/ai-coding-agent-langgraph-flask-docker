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

logger = logging.getLogger(__name__)


async def get_template_context() -> dict:
    """Build complete template context for dashboard page.

    Returns:
        Dictionary with all template variables.
    """
    dashboard_data = {}
    agent_task = read_db_task()
    if agent_task:
        # logger.info("current node: %s", agent_task.current_node)
        dashboard_data = {
            "task_id": agent_task.task_id,
            "task_name": agent_task.task_name,
            "task_description": agent_task.task_description,
            "task_type": agent_task.task_type,
            "task_skill_level": agent_task.task_skill_level,
            "plan_content": markdown.markdown(agent_task.plan_content)
            if agent_task.plan_content
            else "",
            "plan_state": agent_task.plan_state,
            "plan_exists": bool(agent_task.plan_content),
            "current_node": "todo",
        }
    return dashboard_data


async def move_task_to_in_progress(task_id: str) -> bool:
    """Moves the task to the state in progress."""
    logger.info("Moving task %s to in progress", task_id)
    agent_settings: AgentSettings = settings_service.get_or_create_settings()
    board_provider = create_board_provider(agent_settings)
    await board_provider.move_task_to_named_state(
        task_id, state_name=board_provider.get_task_system().state_in_progress
    )
    return True
