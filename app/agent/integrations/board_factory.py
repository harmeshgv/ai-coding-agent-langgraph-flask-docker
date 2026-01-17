"""
Factory for creating board provider instances.

This module provides a factory function that creates the appropriate board
provider based on the system configuration, enabling easy switching between
different board systems (Trello, GitHub, Jira, etc.).
"""

import logging

from agent.integrations.board_provider import BoardProvider
from agent.integrations.trello_provider import TrelloProvider

logger = logging.getLogger(__name__)


def create_board_provider(sys_config: dict) -> BoardProvider:
    """
    Factory function to create the appropriate board provider.
    
    The provider type is determined by the 'board_provider' key in sys_config.
    If not specified, defaults to 'trello' for backward compatibility.
    
    Args:
        sys_config: System configuration dictionary containing provider type
                   and provider-specific settings
    
    Returns:
        An instance of a BoardProvider implementation
        
    Raises:
        ValueError: If an unknown provider type is specified
        
    Example:
        >>> sys_config = {"board_provider": "trello", ...}
        >>> provider = create_board_provider(sys_config)
    """
    provider_type = sys_config.get("board_provider", "trello").lower()

    logger.info("Creating board provider: %s", provider_type)

    if provider_type == "trello":
        return TrelloProvider(sys_config)

    raise ValueError(
        f"Unknown board provider: {provider_type}. "
        f"Supported providers: trello"
    )
