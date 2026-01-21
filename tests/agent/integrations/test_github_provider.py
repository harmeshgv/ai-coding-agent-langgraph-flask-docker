"""Tests for the GitHub board provider implementation."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.integrations.board_provider import BoardTask
from app.agent.integrations.github_provider import GitHubProvider
from app.core.models import AgentSettings, TaskSystem


@pytest.fixture
def agent_settings():
    """Fixture with GitHub task system configuration."""
    task_system = TaskSystem(
        board_provider="github",
        api_key="token",
        token="token",
        board_id="proj_123",
    )
    settings = AgentSettings(task_system_type="GITHUB")
    settings.task_systems = [task_system]
    task_system.agent_settings = settings
    return settings


@pytest.fixture
def github_provider(agent_settings):
    """Fixture for GitHubProvider instance."""
    return GitHubProvider(agent_settings)


@pytest.mark.asyncio
async def test_get_task(github_provider):
    """Ensure get_task maps project item fields into BoardTask."""
    mock_item = {
        "id": "item123",
        "title": "Example Task",
        "body": "Details",
        "state_id": "state456",
        "state_name": "In Progress",
        "url": "https://github.com/org/repo/issues/1",
    }

    with patch(
        "app.agent.integrations.github_provider.get_project_item",
        new=AsyncMock(return_value=mock_item),
    ) as mock_get:
        task = await github_provider.get_task("item123")

        mock_get.assert_called_once_with("item123", github_provider.agent_settings)
        assert isinstance(task, BoardTask)
        assert task.id == "item123"
        assert task.name == "Example Task"
        assert task.description == "Details"
        assert task.state_id == "state456"
        assert task.state_name == "In Progress"
        assert task.url == "https://github.com/org/repo/issues/1"
