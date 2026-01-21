"""
GitHub Projects v2 implementation of the BoardProvider interface.

This module provides a GitHubProvider class that wraps the GitHub Projects v2
GraphQL API client and implements the BoardProvider interface for consistent
board operations across different systems.
"""

import logging
from datetime import datetime, timezone

from app.agent.integrations.board_provider import (
    BoardComment,
    BoardProvider,
    BoardStateMove,
    BoardTask,
)
from app.agent.integrations.github_client import (
    add_comment_to_issue,
    create_draft_issue,
    get_issue_comments,
    get_items_from_column,
    get_item_status_history,
    get_project_columns,
    move_item_to_column,
    move_item_to_named_column,
)
from app.core.models import AgentSettings

logger = logging.getLogger(__name__)


class GitHubProvider(BoardProvider):
    """
    GitHub Projects v2 implementation of the BoardProvider interface.

    This class wraps the GitHub GraphQL API client functions and provides
    a consistent interface for board operations.
    """

    def __init__(self, agent_settings: AgentSettings):
        """
        Initialize the GitHub provider.

        Args:
            agent_settings: Agent settings containing GitHub project configuration.
        """
        self.agent_settings = agent_settings

    async def get_states(self) -> list[dict]:
        """Fetch all states (columns) from the GitHub Project."""
        return await get_project_columns(self.agent_settings)

    async def get_tasks_from_state(self, state_id: str) -> list[BoardTask]:
        """
        Fetch all tasks from a specific state (column).

        Note: For GitHub Projects, we need to resolve the column name from ID
        first, then fetch items. The state_id here is the column option ID.
        """
        columns = await get_project_columns(self.agent_settings)
        target_column = next(
            (col for col in columns if col["id"] == state_id), None
        )

        if not target_column:
            logger.warning("Column with ID %s not found", state_id)
            return []

        items = await get_items_from_column(target_column["name"], self.agent_settings)

        return [
            BoardTask(
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

    async def get_comments(self, task_id: str) -> list[BoardComment]:
        """Fetch all comments for a GitHub task."""
        comments = await get_issue_comments(task_id, self.agent_settings)

        return [
            BoardComment(
                id=comment["id"],
                text=comment["text"],
                author=comment["member_creator"],
                date=self._parse_timestamp(comment["date"]),
            )
            for comment in comments
        ]

    async def get_state_moves(self, task_id: str) -> list[BoardStateMove]:
        """
        Fetch the history of state moves (column changes) for a task.

        Note: GitHub Projects v2 doesn't provide direct access to field change
        history through the API. This returns an empty list.
        """
        moves = await get_item_status_history(task_id, self.agent_settings)

        return [
            BoardStateMove(
                id=move["id"],
                date=self._parse_timestamp(move.get("date")),
                state_before=move.get("state_before"),
                state_after=move.get("state_after"),
            )
            for move in moves
        ]

    async def create_task(
        self, name: str, description: str, state_name: str
    ) -> BoardTask:
        """Create a new task (draft issue) in the specified state (column)."""
        result = await create_draft_issue(
            name,
            description,
            state_name,
            self.agent_settings,
        )

        return BoardTask(
            id=result["id"],
            name=result["title"],
            description=description,
            state_id="",
            state_name=result["column"],
            url=result.get("url", ""),
        )

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
