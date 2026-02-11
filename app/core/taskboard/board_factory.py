"""
Factory for creating board provider instances.

This module provides a factory function that creates the appropriate board
provider based on the system configuration, enabling easy switching between
different board systems (Trello, GitHub, Jira, etc.).
"""

import logging

from app.core.taskboard.board_provider import BoardProvider
from app.core.taskboard.github_provider import GitHubProvider
from app.core.taskboard.trello_provider import TrelloProvider
from app.core.localdb.models import AgentSettings

logger = logging.getLogger(__name__)


def create_board_provider(agent_settings: AgentSettings) -> BoardProvider:
    """
    Factory function to create the appropriate board provider.

    The provider type is determined by the 'board_provider' key inside
    AgentSettings.task_system_type.
    If not specified, defaults to 'trello' for backward compatibility.

    Args:
        agent_settings: Agent settings containing system configuration details

    Returns:
        An instance of a BoardProvider implementation

    Raises:
        ValueError: If an unknown provider type is specified

    Example:
        >>> agent_settings = AgentSettings(task_system_type="TRELLO", ...})
        >>> provider = create_board_provider(agent_settings)
    """
    provider_type = agent_settings.task_system_type.lower()

    logger.info("Creating board provider: %s", provider_type)

    if provider_type == "trello":
        return TrelloProvider(agent_settings)

    if provider_type == "github":
        return GitHubProvider(agent_settings)

    raise ValueError(
        f"Unknown board provider: {provider_type}. Supported providers: trello, github"
    )
