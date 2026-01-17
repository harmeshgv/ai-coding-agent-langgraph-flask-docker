"""
Tests for the board provider factory.
"""

import pytest

from agent.integrations.board_factory import create_board_provider
from agent.integrations.board_provider import BoardProvider
from agent.integrations.trello_provider import TrelloProvider


def test_create_trello_provider():
    """Test creating a Trello provider."""
    sys_config = {"board_provider": "trello"}
    provider = create_board_provider(sys_config)
    
    assert isinstance(provider, BoardProvider)
    assert isinstance(provider, TrelloProvider)


def test_create_trello_provider_default():
    """Test that Trello is the default provider."""
    sys_config = {}
    provider = create_board_provider(sys_config)
    
    assert isinstance(provider, TrelloProvider)


def test_create_unknown_provider_raises_error():
    """Test that unknown provider raises ValueError."""
    sys_config = {"board_provider": "unknown"}
    
    with pytest.raises(ValueError, match="Unknown board provider: unknown"):
        create_board_provider(sys_config)
