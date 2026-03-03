"""
Tests for the task update node.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.taskprovider.task_provider import ProviderTask
from app.agent.nodes.task_update_node import (
    AGENT_DEFAULT_COMMENT,
    _build_agent_comments,
    _check_for_task_creation,
    create_task_update_node,
    get_agent_result,
)
from app.core.localdb.models import AgentSettings, TaskSystem


@pytest.fixture
def agent_settings():
    """Fixture for agent configuration."""
    settings = AgentSettings(task_system_type="TRELLO")
    task_system = TaskSystem(
        task_system_type="TRELLO",
        task_provider="trello",
        state_in_review="Done",
    )
    settings.task_systems.append(task_system)
    return settings


@pytest.fixture
def mock_task_provider():
    """Fixture for mock task provider."""
    provider = MagicMock()
    provider.add_comment = AsyncMock()
    provider.move_task_to_named_state = AsyncMock(return_value="list3")
    mock_task_system = MagicMock()
    mock_task_system.state_in_review = "Done"
    provider.get_task_system = MagicMock(return_value=mock_task_system)
    return provider


@pytest.mark.asyncio
async def test_task_update_node_success(agent_settings, mock_task_provider, monkeypatch):
    """Test successful task update."""
    state = {
        "provider_task": ProviderTask(
            id="card1",
            name="Task Name",
            description="Desc",
            state_id="list1",
            state_name="In Progress",
        ),
        "messages": [],
        "agent_summary": ["Task completed successfully"],
        "current_node": "any_node",
    }

    monkeypatch.setattr(
        "app.agent.nodes.task_update_node.create_task_provider",
        lambda *_: mock_task_provider,
    )
    task_update = create_task_update_node(agent_settings)
    result = await task_update(state)

    assert result["current_node"] == "task_update"
    mock_task_provider.add_comment.assert_called()
    mock_task_provider.move_task_to_named_state.assert_called_once_with(
        task_id="card1", state_name="Done"
    )


@pytest.mark.asyncio
async def test_task_update_node_no_task_id(agent_settings, mock_task_provider, monkeypatch):
    """Test task update with no task ID."""
    state = {"provider_task": None, "messages": [], "current_node": "any_node"}

    monkeypatch.setattr(
        "app.agent.nodes.task_update_node.create_task_provider",
        lambda *_: mock_task_provider,
    )
    task_update = create_task_update_node(agent_settings)
    result = await task_update(state)

    assert result == {}
    mock_task_provider.add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_task_update_node_move_fails(agent_settings, mock_task_provider, monkeypatch):
    """Test task update when move operation fails."""
    state = {
        "provider_task": ProviderTask(
            id="card1",
            name="Task Name",
            description="Desc",
            state_id="list1",
            state_name="In Progress",
        ),
        "messages": [],
        "agent_summary": [],
        "current_node": "any_node",
    }
    mock_task_provider.move_task_to_named_state = AsyncMock(
        side_effect=ValueError("State not found")
    )

    monkeypatch.setattr(
        "app.agent.nodes.task_update_node.create_task_provider",
        lambda *_: mock_task_provider,
    )
    task_update = create_task_update_node(agent_settings)
    result = await task_update(state)

    assert result is None


def test_get_agent_result_with_finish_task():
    """Test extracting agent result from finish_task tool call."""
    messages = [
        HumanMessage(content="Do something"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "finish_task",
                    "args": {"summary": "Task completed successfully"},
                }
            ],
        ),
    ]

    result = get_agent_result(messages)
    assert result == "Task completed successfully"


def test_get_agent_result_no_finish_task():
    """Test extracting agent result when no finish_task is present."""
    messages = [HumanMessage(content="Do something")]

    result = get_agent_result(messages)
    assert result == AGENT_DEFAULT_COMMENT


def test_check_for_task_creation_found():
    """Test detecting task creation in messages."""
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call1",
                        "name": "create_task",
                        "args": {"title": "New Task"},
                    }
                ],
            ),
            ToolMessage(
                content="Successfully created implementation task: #123",
                tool_call_id="call1",
            ),
        ]
    }

    was_created, info = _check_for_task_creation(state)
    assert was_created is True
    assert "Successfully created implementation task" in info


def test_check_for_task_creation_wrong_tool():
    """Test when a different tool is called."""
    state = {"messages": [HumanMessage(content="Do something")]}

    was_created, info = _check_for_task_creation(state)
    assert was_created is False
    assert info is None


def test_build_agent_comments_with_summary():
    """Test building agent comments with summary entries."""
    state = {
        "messages": [],
        "agent_summary": ["Analysis complete", "Code updated"],
    }

    comments = _build_agent_comments(state)
    assert len(comments) == 2
    assert "Analysis complete" in comments[0]
    assert "Code updated" in comments[1]


def test_build_agent_comments_no_summary():
    """Test building agent comments without summary entries."""
    state = {"messages": [], "agent_summary": []}

    comments = _build_agent_comments(state)
    assert len(comments) == 1
    assert comments[0] == AGENT_DEFAULT_COMMENT


def test_build_agent_comments_with_card_creation():
    """Test building agent comments when a new task was created."""
    state = {
        "agent_summary": ["Analysis complete"],
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call1",
                        "name": "create_task",
                        "args": {"title": "New Feature"},
                    }
                ],
            ),
            ToolMessage(
                content="Successfully created implementation task: 'New Feature'\nCard URL: https://trello.com/c/abc123",
                tool_call_id="call1",
            ),
        ],
    }

    comments = _build_agent_comments(state)
    assert len(comments) == 2
    assert "Analysis complete" in comments[0]
    assert "New Implementation Task Created" in comments[1]
