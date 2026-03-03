"""
Factory for creating task provider instances.

This module provides a factory function that creates the appropriate task
provider based on the system configuration, enabling easy switching between
different task systems (Trello, GitHub, Jira, etc.).
"""

import logging

from app.core.taskprovider.task_provider import TaskProvider
from app.core.taskprovider.github_provider import GitHubProvider
from app.core.taskprovider.trello_provider import TrelloProvider
from app.core.localdb.models import AgentSettings

logger = logging.getLogger(__name__)


def create_task_provider(agent_settings: AgentSettings) -> TaskProvider:
    """
    Factory function to create the appropriate task provider.

    The provider type is determined by the 'task_provider' key inside
    AgentSettings.task_system_type.
    If not specified, defaults to 'trello' for backward compatibility.

    Args:
        agent_settings: Agent settings containing system configuration details

    Returns:
        An instance of a TaskProvider implementation

    Raises:
        ValueError: If an unknown provider type is specified

    Example:
        >>> agent_settings = AgentSettings(task_system_type="TRELLO", ...})
        >>> provider = create_task_provider(agent_settings)
    """
    provider_type = agent_settings.task_system_type.lower()

    logger.info("Creating task provider: %s", provider_type)

    if provider_type == "trello":
        return TrelloProvider(agent_settings)

    if provider_type == "github":
        return GitHubProvider(agent_settings)

    raise ValueError(f"Unknown task provider: {provider_type}. Supported providers: trello, github")
