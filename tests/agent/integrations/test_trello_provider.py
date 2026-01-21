"""
Tests for the Trello board provider implementation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.integrations.board_provider import BoardTask, BoardComment, BoardStateMove
from app.agent.integrations.trello_provider import TrelloProvider
from app.core.models import AgentSettings, TaskSystem


@pytest.fixture
def agent_settings():
    """Fixture for agent configuration."""
    task_system = TaskSystem(
        board_provider="trello",
        api_key="test_key",
        token="test_token",
        board_id="test_board_id",
    )
    settings = AgentSettings(task_system_type="TRELLO")
    settings.task_system = task_system
    return settings


@pytest.fixture
def trello_provider(agent_settings):
    """Fixture for TrelloProvider instance."""
    return TrelloProvider(agent_settings)


@pytest.mark.asyncio
async def test_get_states(trello_provider):
    """Test getting states (Trello lists) from board."""
    mock_lists = [
        {"id": "list1", "name": "To Do"},
        {"id": "list2", "name": "In Progress"},
    ]
    
    with patch(
        "app.agent.integrations.trello_provider.get_all_trello_lists",
        new=AsyncMock(return_value=mock_lists),
    ):
        states = await trello_provider.get_states()
        
        assert states == mock_lists


@pytest.mark.asyncio
async def test_get_tasks_from_state(trello_provider):
    """Test getting tasks from a state (Trello list)."""
    mock_cards = [
        {"id": "card1", "name": "Task 1", "desc": "Description 1", "url": "http://test1"},
        {"id": "card2", "name": "Task 2", "desc": "Description 2", "url": "http://test2"},
    ]
    
    with patch(
        "app.agent.integrations.trello_provider.get_all_trello_cards",
        new=AsyncMock(return_value=mock_cards),
    ):
        tasks = await trello_provider.get_tasks_from_state("list1")
        
        assert len(tasks) == 2
        assert all(isinstance(task, BoardTask) for task in tasks)
        assert tasks[0].id == "card1"
        assert tasks[0].name == "Task 1"
        assert tasks[0].description == "Description 1"


@pytest.mark.asyncio
async def test_move_task_to_state(trello_provider):
    """Test moving a task to a different state (Trello list)."""
    with patch(
        "app.agent.integrations.trello_provider.move_trello_card_to_list",
        new=AsyncMock(),
    ) as mock_move:
        await trello_provider.move_task_to_state("card1", "list2")
        
        mock_move.assert_called_once_with("card1", "list2", trello_provider.agent_settings)


@pytest.mark.asyncio
async def test_move_task_to_named_state(trello_provider):
    """Test moving a task to a state by name (Trello list)."""
    with patch(
        "app.agent.integrations.trello_provider.move_trello_card_to_named_list",
        new=AsyncMock(return_value="list2"),
    ) as mock_move:
        state_id = await trello_provider.move_task_to_named_state("card1", "In Progress")
        
        assert state_id == "list2"
        mock_move.assert_called_once()


@pytest.mark.asyncio
async def test_add_comment(trello_provider):
    """Test adding a comment to a card."""
    with patch(
        "app.agent.integrations.trello_provider.add_comment_to_trello_card",
        new=AsyncMock(),
    ) as mock_add:
        await trello_provider.add_comment("card1", "Test comment")
        
        mock_add.assert_called_once_with("card1", "Test comment", trello_provider.agent_settings)


@pytest.mark.asyncio
async def test_get_comments(trello_provider):
    """Test getting comments from a card."""
    mock_comments = [
        {
            "id": "comment1",
            "text": "Great work!",
            "member_creator": "John Doe",
            "date": "2024-01-01T12:00:00Z",
        },
    ]
    
    with patch(
        "app.agent.integrations.trello_provider.get_trello_card_comments",
        new=AsyncMock(return_value=mock_comments),
    ):
        comments = await trello_provider.get_comments("card1")
        
        assert len(comments) == 1
        assert all(isinstance(comment, BoardComment) for comment in comments)
        assert comments[0].id == "comment1"
        assert comments[0].text == "Great work!"
        assert comments[0].author == "John Doe"
        assert isinstance(comments[0].date, datetime)


@pytest.mark.asyncio
async def test_get_state_moves(trello_provider):
    """Test getting state move history (Trello list moves) for a card."""
    mock_moves = [
        {
            "id": "move1",
            "date": "2024-01-01T12:00:00Z",
            "list_before": "To Do",
            "list_after": "In Progress",
        }
    ]
    
    with patch(
        "app.agent.integrations.trello_provider.get_trello_card_list_moves",
        new=AsyncMock(return_value=mock_moves),
    ):
        moves = await trello_provider.get_state_moves("card1")
        
        assert len(moves) == 1
        assert all(isinstance(move, BoardStateMove) for move in moves)
        assert moves[0].id == "move1"
        assert moves[0].state_before == "To Do"
        assert moves[0].state_after == "In Progress"


@pytest.mark.asyncio
async def test_create_card(trello_provider):
    """Test creating a new card."""
    mock_result = {
        "id": "new_card",
        "name": "New Task",
        "url": "https://trello.com/c/new_card",
        "list": "To Do",
    }
    
    with patch(
        "app.agent.integrations.trello_provider.create_trello_card",
        new=AsyncMock(return_value=mock_result),
    ):
        task = await trello_provider.create_task("New Task", "Description", "To Do")
        
        assert isinstance(task, BoardTask)
        assert task.id == "new_card"
        assert task.name == "New Task"
        assert task.state_name == "To Do"


def test_parse_timestamp_valid(trello_provider):
    """Test parsing a valid timestamp."""
    timestamp = "2024-01-01T12:00:00Z"
    result = trello_provider._parse_timestamp(timestamp)
    
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_parse_timestamp_none(trello_provider):
    """Test parsing None timestamp returns current time."""
    result = trello_provider._parse_timestamp(None)
    
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_parse_timestamp_invalid(trello_provider):
    """Test parsing invalid timestamp returns current time."""
    result = trello_provider._parse_timestamp("invalid")
    
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
