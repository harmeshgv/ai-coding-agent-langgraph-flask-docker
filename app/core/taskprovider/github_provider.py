"""
GitHub Projects v2 implementation of the TaskProvider interface.

This module provides a GitHubProvider class that wraps the GitHub Projects v2
GraphQL API client and implements the TaskProvider interface for consistent
task operations across different systems.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.taskprovider.task_provider import (
    ProviderTaskComment,
    TaskProvider,
    ProviderTaskStateMove,
    ProviderTask,
)
from app.core.taskprovider.github_client import (
    add_comment_to_issue,
    create_draft_issue,
    get_issue_comments,
    get_item_status_history,
    get_items_from_column,
    get_project_columns,
    get_project_item,
    move_item_to_column,
    move_item_to_named_column,
)
from app.core.localdb.models import AgentSettings, TaskSystem

logger = logging.getLogger(__name__)


class GitHubProvider(TaskProvider):
    """
    GitHub Projects v2 implementation of the TaskProvider interface.

    This class wraps the GitHub GraphQL API client functions and provides
    a consistent interface for task operations.
    """

    def __init__(self, agent_settings: AgentSettings):
        """
        Initialize the GitHub provider.

        Args:
            agent_settings: Agent settings containing GitHub project configuration.
        """
        self.agent_settings = agent_settings
        self._task_system: TaskSystem | None = agent_settings.get_task_system("github")

    async def get_states(self) -> list[dict]:
        """Fetch all states (columns) from the GitHub Project."""
        return await get_project_columns(self.agent_settings)

    async def get_task(self, task_id: str) -> Optional[ProviderTask]:
        """Fetch a specific task (project item) by ID."""
        item = await get_project_item(task_id, self.agent_settings)

        if not item:
            logger.warning("GitHub Issue %s not found", task_id)
            return None

        return ProviderTask(
            id=item["id"],
            name=item.get("title", ""),
            description=item.get("body", ""),
            state_id=item.get("state_id", ""),
            state_name=item.get("state_name", ""),
            url=item.get("url", ""),
        )

    async def get_tasks_from_state(self, state_id: str) -> list[ProviderTask]:
        """
        Fetch all tasks from a specific state (column).

        Note: For GitHub Projects, we need to resolve the column name from ID
        first, then fetch items. The state_id here is the column option ID.
        """
        columns = await get_project_columns(self.agent_settings)
        target_column = next((col for col in columns if col["id"] == state_id), None)

        if not target_column:
            logger.warning("Column with ID %s not found", state_id)
            return []

        items = await get_items_from_column(target_column["name"], self.agent_settings)

        return [
            ProviderTask(
                id=item["id"],
                name=item["title"],
                description=item["body"] or "",
                state_id=state_id,
                state_name=target_column["name"],
                url=item.get("url", ""),
            )
            for item in items
        ]

    async def move_task_to_state(self, task_id: str, state_id: str) -> None:
        """Move a task to a different state (column)."""
        await move_item_to_column(task_id, state_id, self.agent_settings)

    async def move_task_to_named_state(self, task_id: str, state_name: str) -> str:
        """Move a task to a state (column) identified by name."""
        return await move_item_to_named_column(task_id, state_name, self.agent_settings)

    async def add_comment(self, task_id: str, comment: str) -> None:
        """
        Add a comment to a GitHub task.

        Note: For GitHub Projects, we need the issue ID (content_id), not the
        project item ID. If the task_id is a project item ID, we need to
        extract the content ID first.
        """
        await add_comment_to_issue(task_id, comment, self.agent_settings)

    async def get_comments(self, task_id: str) -> list[ProviderTaskComment]:
        """Fetch all comments for a GitHub task."""
        comments = await get_issue_comments(task_id, self.agent_settings)

        return [
            ProviderTaskComment(
                id=comment["id"],
                text=comment["text"],
                author=comment["member_creator"],
                date=self._parse_timestamp(comment["date"]),
            )
            for comment in comments
        ]

    async def get_state_moves(self, task_id: str) -> list[ProviderTaskStateMove]:
        """
        Fetch the history of state moves (column changes) for a task.

        Note: GitHub Projects v2 doesn't provide direct access to field change
        history through the API. This returns an empty list.
        """
        moves = await get_item_status_history(task_id, self.agent_settings)

        return [
            ProviderTaskStateMove(
                id=move["id"],
                date=self._parse_timestamp(move.get("date")),
                state_before=move.get("state_before"),
                state_after=move.get("state_after"),
            )
            for move in moves
        ]

    async def create_task(self, name: str, description: str, state_name: str) -> ProviderTask:
        """Create a new task (draft issue) in the specified state (column)."""
        result = await create_draft_issue(
            name,
            description,
            state_name,
            self.agent_settings,
        )

        return ProviderTask(
            id=result["id"],
            name=result["title"],
            description=description,
            state_id="",
            state_name=result["column"],
            url=result.get("url", ""),
        )

    def get_type(self) -> str:
        """Return the provider identifier."""
        return "github"

    def get_task_system(self) -> TaskSystem | None:
        """Return the configured GitHub TaskSystem if available."""
        return self._task_system

    def _parse_timestamp(self, value: str | None) -> datetime:
        """
        Parse a GitHub timestamp string into a datetime object.

        Args:
            value: ISO format timestamp string.

        Returns:
            Parsed datetime object with timezone info.
        """
        if not value:
            return datetime.now(timezone.utc)

        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            logger.warning("Failed to parse GitHub timestamp '%s'", value)
            return datetime.now(timezone.utc)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed
