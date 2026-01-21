"""Service layer for dashboard functionality.

This module contains business logic for the dashboard page,
separating concerns from the route handlers.
"""

import logging
import os

logger = logging.getLogger(__name__)


class DashboardService:
    """Service for dashboard-related operations."""

    @staticmethod
    def get_plan_content() -> str:
        """Read and return the plan.md content from workspace.

        Returns:
            Content of plan.md or a default message if not found.
        """
        workspace_path = os.environ.get("WORKSPACE", ".")
        plan_path = os.path.join(workspace_path, "plan.md")

        if not os.path.exists(plan_path):
            return "No plan.md found in workspace."

        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                return f.read()
        except (IOError, OSError) as e:
            logger.error("Error reading plan.md: %s", e)
            return f"Error reading plan.md: {e}"

    @staticmethod
    def get_template_context() -> dict:
        """Build complete template context for dashboard page.

        Returns:
            Dictionary with all template variables.
        """
        return {
            "plan_content": DashboardService.get_plan_content(),
        }
