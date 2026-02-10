"""Service function for the plan."""

import logging
import os

from app.agent.utils import get_workspace

logger = logging.getLogger(__name__)


def delete_plan():
    """Remove the plan.md content from the workspace."""
    workspace_path = get_workspace()
    plan_path = os.path.join(workspace_path, "plan.md")

    if os.path.exists(plan_path):
        os.remove(plan_path)  # Alternativ: os.unlink(datei_pfad)
        print("plan.md is removed")


def exist_plan() -> bool:
    """Check if the plan.md exists in the workspace.

    Returns:
        True if plan.md exists, False otherwise.
    """
    workspace_path = get_env_settings().workspace
    plan_path = os.path.join(workspace_path, "plan.md")
    return os.path.exists(plan_path)


def get_plan() -> str:
    """Read and return the plan.md content from workspace.

    Returns:
        Content of plan.md or a default message if not found.
    """
    workspace_path = get_workspace()
    plan_path = os.path.join(workspace_path, "plan.md")

    if not os.path.exists(plan_path):
        return "No plan.md found in workspace."

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            return f.read()
    except (IOError, OSError) as e:
        logger.error("Error reading plan.md: %s", e)
        return f"Error reading plan.md: {e}"
