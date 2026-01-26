"""Service layer for dashboard functionality.

This module contains business logic for the dashboard page,
separating concerns from the route handlers.
"""

import json
import logging
import os

from app.core.plan_services import get_plan

logger = logging.getLogger(__name__)


def get_template_context() -> dict:
    """Build complete template context for dashboard page.

    Returns:
        Dictionary with all template variables.
    """
    return {
        "plan_content": get_plan(),
        "agent_state": get_agent_state(),
    }


def get_agent_state() -> dict:
    """Read and return the agent_state.json content from workspace.

    Returns:
        A dictionary with the agent's state or default values if not found.
    """
    workspace_path = os.environ.get("WORKSPACE", ".")
    state_file_path = os.path.join(workspace_path, "agent_state.json")

    default_state = {
        "task_id": None,
        "task_name": None,
        "task_skill_level": None,
        "plan_state": None,
    }

    if not os.path.exists(state_file_path):
        logger.info("No agent_state.json found in workspace.")
        return default_state

    try:
        with open(state_file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, OSError, json.JSONDecodeError) as e:
        logger.error("Error reading or parsing agent_state.json: %s", e)
        return default_state
