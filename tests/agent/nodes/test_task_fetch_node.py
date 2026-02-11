"""
Tests for the task fetch node.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.taskboard.board_provider import BoardComment, BoardTask
from app.agent.nodes.task_fetch_node import (
    create_task_fetch_node,
    fetch_task_from_state,
)
from app.core.task_utils import (
    filter_comments_between_timestamps,
    get_latest_move_to_in_progress,
)
from app.core.localdb.models import AgentSettings, TaskSystem


@pytest.fixture
def agent_settings():
    """Fixture for agent configuration."""
    settings = AgentSettings(task_system_type="TRELLO")
    task_system = TaskSystem(
        task_system_type="TRELLO",
        board_provider="trello",
        state_backlog="Backlog",
        state_todo="To Do",
        state_in_progress="In Progress",
        state_in_review="In Review",
    )
    settings.task_systems.append(task_system)
    return settings


@pytest.fixture
def mock_board_provider():
    """Fixture for mock board provider."""
    provider = MagicMock()
    provider.get_states = AsyncMock(
        return_value=[
            {"id": "list1", "name": "To Do"},
            {"id": "list2", "name": "In Progress"},
            {"id": "list3", "name": "In Review"},
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
    provider.get_task = AsyncMock(
        return_value=BoardTask(
            id="card1",
            name="Test Task",
            description="Moved Description",
            state_id="list2",
            state_name="In Progress",
        )
    )

    return provider


@pytest.mark.asyncio
async def test_task_fetch_node_success(agent_settings, mock_board_provider):
    """Test successful task fetch from todo state."""
    with (
        patch(
            "app.agent.nodes.task_fetch_node.create_board_provider",
            return_value=mock_board_provider,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.read_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.fetch_task_from_state",
            new=AsyncMock(
                return_value=BoardTask(
                    id="card1",
                    name="Test Task",
                    description="Test Description",
                    state_id="list1",
                    state_name="To Do",
                )
            ),
        ),
        patch(
            "app.agent.nodes.task_fetch_node.move_task_to_state",
            new=AsyncMock(
                return_value=BoardTask(
                    id="card1",
                    name="Test Task",
                    description="Test Description",
                    state_id="list2",
                    state_name="In Progress",
                )
            ),
        ),
        patch(
            "app.agent.nodes.task_fetch_node.create_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.delete_db_task",
        ),
    ):
        task_fetch = create_task_fetch_node(agent_settings)
        result = await task_fetch({})

        assert result["task"].id == "card1"
        assert result["task"].name == "Test Task"
        assert result["task"].state_id == "list2"  # Moved to in-progress state
        assert result["current_node"] == "task_fetch"
        assert result["task_comments"] == []
        assert result["pr_review_message"] == ""


@pytest.mark.asyncio
async def test_task_fetch_node_no_review_list(agent_settings, mock_board_provider):
    """Test task fetch when no review list is configured - should still fetch from To Do."""
    temp_settings = AgentSettings(task_system_type="TRELLO")
    task_system = TaskSystem(
        task_system_type="TRELLO",
        board_provider="trello",
        state_backlog="Backlog",
        state_todo="To Do",
        state_in_progress="In Progress",
        state_in_review=None,
    )
    temp_settings.task_systems.append(task_system)

    with (
        patch(
            "app.agent.nodes.task_fetch_node.create_board_provider",
            return_value=mock_board_provider,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.read_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.fetch_task_from_state",
            new=AsyncMock(
                return_value=BoardTask(
                    id="card1",
                    name="Test Task",
                    description="Test Description",
                    state_id="list1",
                    state_name="To Do",
                )
            ),
        ),
        patch(
            "app.agent.nodes.task_fetch_node.move_task_to_state",
            new=AsyncMock(
                return_value=BoardTask(
                    id="card1",
                    name="Test Task",
                    description="Test Description",
                    state_id="list2",
                    state_name="In Progress",
                )
            ),
        ),
        patch(
            "app.agent.nodes.task_fetch_node.create_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.delete_db_task",
        ),
    ):
        task_fetch = create_task_fetch_node(temp_settings)
        result = await task_fetch({})

        # Should still fetch task from To Do even without review list
        assert result["task"] is not None
        assert result["task"].id == "card1"
        assert result["task"].state_id == "list2"  # Moved to in-progress


@pytest.mark.asyncio
async def test_task_fetch_node_no_cards(agent_settings, mock_board_provider):
    """Test task fetch when no tasks are available."""
    mock_board_provider.get_tasks_from_state = AsyncMock(return_value=[])

    with (
        patch(
            "app.agent.nodes.task_fetch_node.create_board_provider",
            return_value=mock_board_provider,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.read_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.fetch_task_from_state",
            new=AsyncMock(return_value=None),
        ),
    ):
        task_fetch = create_task_fetch_node(agent_settings)
        result = await task_fetch({})

        assert result["task"] is None


@pytest.mark.asyncio
async def test_task_fetch_node_with_comments(agent_settings, mock_board_provider):
    """Test task fetch with comments when task is already in In Progress (returned from review)."""
    from app.core.localdb.models import Task

    # Create a mock db_task to simulate an existing task
    mock_db_task = Task(
        task_id="card1",
        task_name="Test Task",
        branch_name="feature/test",
    )

    # Mock board provider to return task in "In Progress" state
    mock_board_provider.get_task = AsyncMock(
        return_value=BoardTask(
            id="card1",
            name="Test Task",
            description="Test Description",
            state_id="list2",
            state_name="In Progress",
        )
    )

    # Comment within the review period
    mock_comments = [
        BoardComment(
            id="comment1",
            text="Please fix the bug",
            author="John Doe",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
    ]

    with (
        patch(
            "app.agent.nodes.task_fetch_node.create_board_provider",
            return_value=mock_board_provider,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.read_db_task",
            return_value=mock_db_task,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.fetch_review_comments",
            new=AsyncMock(return_value=mock_comments),
        ),
        patch(
            "app.agent.nodes.task_fetch_node._fetch_pr_review_info",
            return_value="",
        ),
    ):
        task_fetch = create_task_fetch_node(agent_settings)
        result = await task_fetch({})

        # Comments should be included since task was already in In Progress (returned from review)
        assert result["task_comments"] is not None
        assert len(result["task_comments"]) == 1
        assert result["task_comments"][0].text == "Please fix the bug"


@pytest.mark.asyncio
async def test_task_fetch_node_no_comments_from_todo(agent_settings, mock_board_provider):
    """Test that comments are NOT included when task is picked from To Do (not from review)."""
    from app.core.taskboard.board_provider import BoardStateMove

    # Task is in "To Do" state (not returned from review)
    mock_board_provider.get_tasks_from_state = AsyncMock(
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

    # Even if there are state moves and comments, they should not be included
    mock_moves = [
        BoardStateMove(
            id="move1",
            date=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            state_before="In Progress",
            state_after="In Review",
        ),
    ]
    mock_board_provider.get_state_moves = AsyncMock(return_value=mock_moves)

    mock_comments = [
        BoardComment(
            id="comment1",
            text="Some comment",
            author="John Doe",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
    ]
    mock_board_provider.get_comments = AsyncMock(return_value=mock_comments)

    with (
        patch(
            "app.agent.nodes.task_fetch_node.create_board_provider",
            return_value=mock_board_provider,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.read_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.fetch_task_from_state",
            new=AsyncMock(
                return_value=BoardTask(
                    id="card1",
                    name="Test Task",
                    description="Test Description",
                    state_id="list1",
                    state_name="To Do",
                )
            ),
        ),
        patch(
            "app.agent.nodes.task_fetch_node.create_db_task",
            return_value=None,
        ),
        patch(
            "app.agent.nodes.task_fetch_node.delete_db_task",
        ),
        patch(
            "app.agent.nodes.task_fetch_node.delete_plan",
        ),
    ):
        task_fetch = create_task_fetch_node(agent_settings)
        result = await task_fetch({})

        # Comments should NOT be included since task was picked from To Do
        assert result["task_comments"] is not None
        assert len(result["task_comments"]) == 0


@pytest.mark.asyncio
async def test_fetch_task_from_state_success(mock_board_provider):
    """Test fetching a task from a state."""
    result = await fetch_task_from_state(
        mock_board_provider,
        "To Do",
    )

    assert result is not None
    assert result.id == "card1"
    assert result.state_id == "list1"
    assert result.state_name == "To Do"


@pytest.mark.asyncio
async def test_fetch_task_from_state_not_found(mock_board_provider):
    """Test fetching from a non-existent state."""
    result = await fetch_task_from_state(
        mock_board_provider,
        "Non-existent",
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_latest_move_to_in_progress(mock_board_provider):
    """Test getting latest move from review to in-progress."""
    from app.core.taskboard.board_provider import BoardStateMove

    mock_moves = [
        BoardStateMove(
            id="move1",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            state_before="To Do",
            state_after="In Review",
        ),
        BoardStateMove(
            id="move2",
            date=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            state_before="In Review",
            state_after="In Progress",
        ),
    ]
    mock_board_provider.get_state_moves = AsyncMock(return_value=mock_moves)

    result = await get_latest_move_to_in_progress(
        mock_board_provider, "card1", "In Review", "In Progress"
    )

    assert result is not None
    assert "review_timestamp" in result
    assert "return_timestamp" in result
    assert isinstance(result["review_timestamp"], datetime)
    assert isinstance(result["return_timestamp"], datetime)


def test_filter_comments_between_timestamps():
    """Test filtering comments between two timestamps."""
    start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    comments = [
        BoardComment(
            id="comment1",
            text="Before start",
            author="User1",
            date=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        ),
        BoardComment(
            id="comment2",
            text="Within range",
            author="User2",
            date=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
        ),
        BoardComment(
            id="comment3",
            text="After end",
            author="User3",
            date=datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
        ),
    ]

    filtered = filter_comments_between_timestamps(comments, start, end)

    assert len(filtered) == 1
    assert filtered[0].text == "Within range"
