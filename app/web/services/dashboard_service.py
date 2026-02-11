"""Service layer for dashboard functionality.

This module contains business logic for the dashboard page,
separating concerns from the route handlers.
"""

import json
import logging
import os
import markdown

from app.agent.utils import get_workspace
from app.core.plan_utils import get_plan, exist_plan
from app.core.localdb.db_task_utils import read_db_task

logger = logging.getLogger(__name__)


def get_template_context() -> dict:
    """Build complete template context for dashboard page.

    Returns:
        Dictionary with all template variables.
    """
    plan_content = get_plan()
    agent_state = get_agent_state()
    db_task = read_db_task()
    return {
        "plan_content": plan_content,
        "plan_html": markdown.markdown(plan_content),
        "plan_exists": exist_plan(),
        "agent_state": agent_state,
        "agent_status": agent_state.get("current_node"),
        "task": agent_state.get("task"),
        "db_plan_state": db_task.plan_state if db_task else None,
    }


def get_agent_state() -> dict:
    """Read and return the agent_state.json content from workspace.

    Returns:
        A dictionary with the agent's state or default values if not found.
    """
    workspace_path = get_workspace()
    state_file_path = os.path.join(workspace_path, "agent_state.json")

    default_state = {
        "task": None,
        "task_comments": None,
        "pr_review_message": None,
        "task_type": None,
        "task_skill_level": None,
        "task_skill_level_reasoning": None,
        "agent_stack": None,
        "retry_count": None,
        "test_result": None,
        "error_log": None,
        "git_branch": None,
        "agent_summary": None,
        "plan_state": None,
        "current_node": None,
        "last_update": None,
        "prompt": None,
        "system_prompt": None,
        "tech_stack": None,
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
