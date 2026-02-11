"""
Tests for the board provider factory.
"""

import pytest

from app.core.taskboard.board_factory import create_board_provider
from app.core.taskboard.board_provider import BoardProvider
from app.core.taskboard.trello_provider import TrelloProvider
from app.core.localdb.models import AgentSettings


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
