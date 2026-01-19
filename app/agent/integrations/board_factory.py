"""
Factory for creating board provider instances.

This module provides a factory function that creates the appropriate board
provider based on the system configuration, enabling easy switching between
different board systems (Trello, GitHub, Jira, etc.).
"""

import logging

from app.agent.integrations.board_provider import BoardProvider
from app.agent.integrations.trello_provider import TrelloProvider
from app.core.models import AgentConfig

logger = logging.getLogger(__name__)


def create_board_provider(agent_config: AgentConfig) -> BoardProvider:
    """
    Factory function to create the appropriate board provider.
    
    The provider type is determined by the 'board_provider' key inside
    AgentConfig.system_config.
    If not specified, defaults to 'trello' for backward compatibility.
    
    Args:
        agent_config: Agent configuration containing system configuration settings
    
    Returns:
        An instance of a BoardProvider implementation
        
    Raises:
        ValueError: If an unknown provider type is specified
        
    Example:
        >>> agent_config = AgentConfig(system_config={"board_provider": "trello", ...})
        >>> provider = create_board_provider(agent_config)
    """
    system_config = agent_config.system_config or {}
    provider_type = system_config.get("board_provider", "trello").lower()

    logger.info("Creating board provider: %s", provider_type)

    if provider_type == "trello":
        return TrelloProvider(agent_config)

    raise ValueError(
        f"Unknown board provider: {provider_type}. "
        f"Supported providers: trello"
    )
