"""
Tests for the task fetch node.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import SystemMessage

from app.agent.integrations.board_provider import BoardTask, BoardComment
from app.agent.nodes.task_fetch_node import (
    create_task_fetch_node,
    fetch_task_from_state,
    filter_comments_after_timestamp,
    get_review_transition_timestamp,
)
from app.core.models import AgentConfig


@pytest.fixture
def agent_config():
    """Fixture for agent configuration."""
    return AgentConfig(
        task_system_type="TRELLO",
        task_backlog_state="Backlog",
        task_readfrom_state="To Do",
        task_in_progress_state="In Progress",
        task_moveto_state="Done",
    )


@pytest.fixture
def mock_board_provider():
    """Fixture for mock board provider."""
    provider = MagicMock()
    provider.get_states = AsyncMock(
        return_value=[
            {"id": "list1", "name": "To Do"},
            {"id": "list2", "name": "In Progress"},
            {"id": "list3", "name": "Done"},
        ]
    )
    provider.get_tasks_from_state = AsyncMock(
        return_value=[
            BoardTask(
                id="card1",
                name="Test Task",
                description="Test Description",
                state_id="list1",
                state_name="To Do",
            )
        ]
    )
    provider.get_comments = AsyncMock(return_value=[])
    provider.get_state_moves = AsyncMock(return_value=[])
    provider.move_task_to_named_state = AsyncMock(return_value="list2")
    return provider


@pytest.mark.asyncio
async def test_task_fetch_node_success(agent_config, mock_board_provider):
    """Test successful task fetch."""
    with patch(
        "app.agent.nodes.task_fetch_node.create_board_provider",
        return_value=mock_board_provider,
    ):
        task_fetch = create_task_fetch_node(agent_config)
        result = await task_fetch({})
        
        assert result["task_id"] == "card1"
        assert result["task_name"] == "Test Task"
        assert result["task_state_id"] == "list2"  # Moved to in-progress state
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], SystemMessage)
        assert "Test Task" in result["messages"][0].content
        assert "Test Description" in result["messages"][0].content


@pytest.mark.asyncio
async def test_task_fetch_node_no_review_list(agent_config, mock_board_provider):
    """Test task fetch when no review list is configured."""
    temp_config = AgentConfig(
        task_system_type=agent_config.task_system_type,
        task_backlog_state=agent_config.task_backlog_state,
        task_readfrom_state=agent_config.task_readfrom_state,
        task_in_progress_state=agent_config.task_in_progress_state,
        task_moveto_state=None,
    )
    
    with patch(
        "app.agent.nodes.task_fetch_node.create_board_provider",
        return_value=mock_board_provider,
    ):
        task_fetch = create_task_fetch_node(temp_config)
        result = await task_fetch({})
        
        assert result["task_id"] is None


@pytest.mark.asyncio
async def test_task_fetch_node_no_cards(agent_config, mock_board_provider):
    """Test task fetch when no tasks are available."""
    mock_board_provider.get_tasks_from_state = AsyncMock(return_value=[])
    
    with patch(
        "app.agent.nodes.task_fetch_node.create_board_provider",
        return_value=mock_board_provider,
    ):
        task_fetch = create_task_fetch_node(agent_config)
        result = await task_fetch({})
        
        assert result["task_id"] is None


@pytest.mark.asyncio
async def test_task_fetch_node_with_comments(agent_config, mock_board_provider):
    """Test task fetch with comments."""
    mock_comments = [
        BoardComment(
            id="comment1",
            text="Please fix the bug",
            author="John Doe",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
    ]
    mock_board_provider.get_comments = AsyncMock(return_value=mock_comments)
    
    with patch(
        "app.agent.nodes.task_fetch_node.create_board_provider",
        return_value=mock_board_provider,
    ):
        task_fetch = create_task_fetch_node(agent_config)
        result = await task_fetch({})
        
        # Comments are not included in the initial message, only in task_comments
        assert result["task_comments"] is not None
        assert len(result["task_comments"]) == 1
        assert result["task_comments"][0].text == "Please fix the bug"


@pytest.mark.asyncio
async def test_fetch_task_from_state_success(mock_board_provider):
    """Test fetching a task from a state."""
    result = await fetch_task_from_state(
        mock_board_provider,
        "To Do",
    )
    
    assert result is not None
    assert result["task"].id == "card1"
    assert result["state_id"] == "list1"
    assert result["state_name"] == "To Do"


@pytest.mark.asyncio
async def test_fetch_task_from_state_not_found(mock_board_provider):
    """Test fetching from a non-existent state."""
    result = await fetch_task_from_state(
        mock_board_provider,
        "Non-existent",
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_get_review_transition_timestamp(mock_board_provider):
    """Test getting review transition timestamp."""
    from app.agent.integrations.board_provider import BoardStateMove
    
    mock_moves = [
        BoardStateMove(
            id="move1",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            state_before="In Progress",
            state_after="Done",
        )
    ]
    mock_board_provider.get_state_moves = AsyncMock(return_value=mock_moves)
    
    result = await get_review_transition_timestamp(
        mock_board_provider, "card1", "Done"
    )
    
    assert result is not None
    assert isinstance(result, datetime)


def test_filter_comments_after_timestamp():
    """Test filtering comments after a timestamp."""
    cutoff = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    comments = [
        BoardComment(
            id="comment1",
            text="Before cutoff",
            author="User1",
            date=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        ),
        BoardComment(
            id="comment2",
            text="After cutoff",
            author="User2",
            date=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    
    filtered = filter_comments_after_timestamp(comments, cutoff)
    
    assert len(filtered) == 1
    assert filtered[0].text == "After cutoff"
