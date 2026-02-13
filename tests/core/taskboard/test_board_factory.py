"""
Tests for the board provider factory.
"""

import pytest

from app.core.taskboard.board_factory import create_board_provider
from app.core.taskboard.board_provider import BoardProvider
from app.core.taskboard.github_provider import GitHubProvider
from app.core.taskboard.trello_provider import TrelloProvider
from app.core.localdb.models import AgentSettings, TaskSystem


def test_create_trello_provider():
    """Test creating a Trello provider."""
    agent_settings = AgentSettings(task_system_type="TRELLO")
    provider = create_board_provider(agent_settings)

    assert isinstance(provider, BoardProvider)
    assert isinstance(provider, TrelloProvider)


def test_create_trello_provider_default():
    """Test that Trello is the default provider."""
    agent_settings = AgentSettings(task_system_type="TRELLO")
    provider = create_board_provider(agent_settings)

    assert isinstance(provider, TrelloProvider)


def test_create_unknown_provider_raises_error():
    """Test that unknown provider raises ValueError."""
    agent_settings = AgentSettings(task_system_type="UNKNOWN")

    with pytest.raises(ValueError, match="Unknown board provider: unknown"):
        create_board_provider(agent_settings)


@pytest.mark.parametrize(
    ("system_type", "provider_cls", "provider_key"),
    [
        ("TRELLO", TrelloProvider, "trello"),
        ("GITHUB", GitHubProvider, "github"),
    ],
)
def test_provider_exposes_task_system(system_type, provider_cls, provider_key):
    """Ensure providers return the TaskSystem they rely on."""
    agent_settings = AgentSettings(task_system_type=system_type)
    task_system = TaskSystem(board_provider=provider_key)
    agent_settings.task_systems = [task_system]

    provider = create_board_provider(agent_settings)

    assert isinstance(provider, provider_cls)
    assert provider.get_task_system() is task_system
