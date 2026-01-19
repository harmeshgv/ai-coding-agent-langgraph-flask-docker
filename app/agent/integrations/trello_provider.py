"""
Trello implementation of the BoardProvider interface.

This adapter wraps the existing Trello client functions and adapts them
to the BoardProvider interface, allowing Trello to be used interchangeably
with other board systems.
"""

import logging
from datetime import datetime, timezone

from app.agent.integrations.board_provider import (
    BoardTask,
    BoardComment,
    BoardStateMove,
    BoardProvider,
)
from app.agent.integrations.trello_client import (
    add_comment_to_trello_card,
    create_trello_card,
    get_all_trello_cards,
    get_all_trello_lists,
    get_trello_card_comments,
    get_trello_card_list_moves,
    move_trello_card_to_list,
    move_trello_card_to_named_list,
)
from app.core.models import AgentConfig

logger = logging.getLogger(__name__)


class TrelloProvider(BoardProvider):
    """
    Trello implementation of the BoardProvider interface.
    
    This class wraps the existing Trello client functions and provides
    a consistent interface for board operations.
    """

    def __init__(self, agent_config: AgentConfig):
        """
        Initialize the Trello provider.
        
        Args:
            agent_config: Agent configuration containing Trello credentials and settings
        """
        self.agent_config = agent_config

    async def get_states(self) -> list[dict]:
        """Fetch all states (Trello lists) from the board."""
        return await get_all_trello_lists(self.agent_config)

    async def get_tasks_from_state(self, state_id: str) -> list[BoardTask]:
        """Fetch all tasks from a specific state (Trello list)."""
        # state_id corresponds to Trello list_id
        cards = await get_all_trello_cards(state_id, self.agent_config)

        return [
            BoardTask(
                id=card["id"],
                name=card["name"],
                description=card["desc"],
                state_id=state_id,
                state_name="",
                url=card.get("url", ""),
            )
            for card in cards
        ]

    async def move_task_to_state(self, task_id: str, state_id: str) -> None:
        """Move a task to a different state (Trello list)."""
        # state_id corresponds to Trello list_id
        await move_trello_card_to_list(task_id, state_id, self.agent_config)

    async def move_task_to_named_state(self, task_id: str, state_name: str) -> str:
        """Move a task to a state (Trello list) identified by name."""
        # state_name corresponds to Trello list_name
        return await move_trello_card_to_named_list(
            task_id, state_name, self.agent_config
        )

    async def add_comment(self, task_id: str, comment: str) -> None:
        """Add a comment to a Trello task."""
        await add_comment_to_trello_card(task_id, comment, self.agent_config)

    async def get_comments(self, task_id: str) -> list[BoardComment]:
        """Fetch all comments for a Trello task."""
        comments = await get_trello_card_comments(task_id, self.agent_config)

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
        """Fetch the history of state moves (Trello list moves) for a task."""
        moves = await get_trello_card_list_moves(task_id, self.agent_config)

        return [
            BoardStateMove(
                id=move["id"],
                date=self._parse_timestamp(move["date"]),
                state_before=move["list_before"],
                state_after=move["list_after"],
            )
            for move in moves
        ]

    async def create_task(
        self, name: str, description: str, state_name: str
    ) -> BoardTask:
        """Create a new task in the specified state (Trello list)."""
        # state_name corresponds to Trello list_name
        result = await create_trello_card(
            name,
            description,
            state_name,
            self.agent_config,
        )

        return BoardTask(
            id=result["id"],
            name=result["name"],
            description=description,
            state_id="",
            state_name=result["list"],
            url=result.get("url", ""),
        )

    def _parse_timestamp(self, value: str | None) -> datetime:
        """
        Parse a Trello timestamp string into a datetime object.
        
        Args:
            value: ISO format timestamp string
            
        Returns:
            Parsed datetime object with timezone info
        """
        if not value:
            return datetime.now(timezone.utc)

        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            logger.warning("Failed to parse Trello timestamp '%s'", value)
            return datetime.now(timezone.utc)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed
