"""
Abstract interface for board system integrations.

This module defines the contract that all board providers (Trello, GitHub, Jira, etc.)
must implement. It provides domain models that are independent of any specific
board system implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.localdb.models import TaskSystem


@dataclass
class BoardTask:
    """
    Domain model for a task, independent of the board system.

    Attributes:
        id: Unique identifier for the task
        name: Title/name of the task
        description: Detailed description of the task
        state_id: ID of the state/column containing this task
        state_name: Name of the state/column containing this task
        url: URL to view the task in the board system
    """

    id: str
    name: str
    description: str
    state_id: str
    state_name: str
    url: str = ""


@dataclass
class BoardComment:
    """
    Domain model for a comment on a task.

    Attributes:
        id: Unique identifier for the comment
        text: Content of the comment
        author: Name of the comment author
        date: Timestamp when the comment was created
    """

    id: str
    text: str
    author: str
    date: datetime

    def __str__(self):
        return f"{self.author}: {self.text} ({self.date.isoformat()})"


@dataclass
class BoardStateMove:
    """
    Domain model for tracking when a task moves between states.

    Attributes:
        id: Unique identifier for the move action
        date: Timestamp when the move occurred
        state_before: Name of the state before the move
        state_after: Name of the state after the move
    """

    id: str
    date: datetime
    state_before: str | None
    state_after: str | None


class BoardProvider(ABC):
    """
    Abstract interface for board system operations.

    All board providers (Trello, GitHub Projects, Jira, etc.) must implement
    this interface to ensure consistent behavior across different systems.
    """

    @abstractmethod
    async def get_states(self) -> list[dict]:
        """
        Fetch all states/columns from the board.

        Returns:
            List of dictionaries with 'id' and 'name' keys
        """

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[BoardTask]:
        """
        Fetch a specific task from the board.

        Args:
            task_id: The ID of the task to fetch

        Returns:
            The BoardTask object

        Raises:
            RuntimeError: If task fetching fails
        """

    @abstractmethod
    async def get_tasks_from_state(self, state_id: str) -> list[BoardTask]:
        """
        Fetch all tasks from a specific state.

        Args:
            state_id: The ID of the state to fetch tasks from

        Returns:
            List of BoardTask objects
        """

    @abstractmethod
    async def move_task_to_state(self, task_id: str, state_id: str) -> None:
        """
        Move a task to a different state.

        Args:
            task_id: The ID of the task to move
            state_id: The ID of the target state

        Raises:
            RuntimeError: If the operation fails
        """

    @abstractmethod
    async def move_task_to_named_state(self, task_id: str, state_name: str) -> str:
        """
        Move a task to a state identified by name.

        Args:
            task_id: The ID of the task to move
            state_name: The name of the target state

        Returns:
            The ID of the target state

        Raises:
            ValueError: If the state name is not found
            RuntimeError: If the move operation fails
        """

    @abstractmethod
    async def add_comment(self, task_id: str, comment: str) -> None:
        """
        Add a comment to a task.

        Args:
            task_id: The ID of the task
            comment: The comment text to add

        Raises:
            RuntimeError: If adding the comment fails
        """

    @abstractmethod
    async def get_comments(self, task_id: str) -> list[BoardComment]:
        """
        Fetch all comments for a task.

        Args:
            task_id: The ID of the task

        Returns:
            List of BoardComment objects

        Raises:
            RuntimeError: If fetching comments fails
        """

    @abstractmethod
    async def get_state_moves(self, task_id: str) -> list[BoardStateMove]:
        """
        Fetch the history of state moves for a task.

        Args:
            task_id: The ID of the task

        Returns:
            List of BoardStateMove objects

        Raises:
            RuntimeError: If fetching move history fails
        """

    @abstractmethod
    async def create_task(self, name: str, description: str, state_name: str) -> BoardTask:
        """
        Create a new task in the specified state.

        Args:
            name: The title/name of the task
            description: The description/body of the task
            state_name: The name of the state to create the task in

        Returns:
            The created BoardTask object

        Raises:
            ValueError: If the state name is not found
            RuntimeError: If task creation fails
        """

    @abstractmethod
    def get_type(self) -> str:
        """Return provider identifier (e.g., 'trello', 'github')."""

    @abstractmethod
    def get_task_system(self) -> TaskSystem:
        """Return the TaskSystem configuration backing this provider."""
