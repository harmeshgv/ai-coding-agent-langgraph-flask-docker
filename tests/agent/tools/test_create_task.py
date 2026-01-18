"""Unit tests for create_task tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anyio

from agent.integrations.board_provider import BoardTask
from agent.tools.create_task import create_task_tool


def test_create_task_tool_creates_card_successfully():
    """Test that the tool creates a task successfully with valid config."""
    async def _test():
        sys_config = {
            "board_provider": "trello",
            "task_readfrom_state": "Sprint Backlog",
        }

        mock_task = BoardTask(
            id="task123",
            name="Add Feature X",
            description="Implement feature X with proper tests",
            state_id="list123",
            state_name="Sprint Backlog",
        )
        mock_task.url = "https://trello.com/c/task123"

        mock_provider = MagicMock()
        mock_provider.create_task = AsyncMock(return_value=mock_task)

        with patch(
            "agent.tools.create_task.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_task_tool(sys_config, "Sprint Backlog")
            result = await tool.ainvoke(
                {
                    "title": "Add Feature X",
                    "instructions": "Implement feature X with proper tests",
                }
            )

            mock_provider.create_task.assert_called_once_with(
                name="Add Feature X",
                description="Implement feature X with proper tests",
                state_name="Sprint Backlog",
            )

            assert "Successfully created implementation task" in result
            assert "Add Feature X" in result
            assert "https://trello.com/c/task123" in result
            assert "Sprint Backlog" in result

    anyio.run(_test)


def test_create_task_tool_handles_missing_target_state():
    """Test that the tool handles missing target list configuration."""
    async def _test():
        sys_config = {
            "board_provider": "trello",
        }

        tool = create_task_tool(sys_config, target_state="")
        result = await tool.ainvoke(
            {
                "title": "Test Task",
                "instructions": "Test instructions",
            }
        )

        assert "Error: target state not configured" in result

    anyio.run(_test)


def test_create_task_tool_handles_value_error():
    """Test that the tool handles ValueError from board provider."""
    async def _test():
        sys_config = {
            "board_provider": "trello",
            "task_readfrom_state": "Invalid List",
        }

        mock_provider = MagicMock()
        mock_provider.create_task = AsyncMock(
            side_effect=ValueError("List 'Invalid List' not found")
        )

        with patch(
            "agent.tools.create_task.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_task_tool(sys_config, "Invalid List")
            result = await tool.ainvoke(
                {
                    "title": "Test Task",
                    "instructions": "Test instructions",
                }
            )

            assert "Error:" in result
            assert "List 'Invalid List' not found" in result

    anyio.run(_test)


def test_create_task_tool_handles_runtime_error():
    """Test that the tool handles RuntimeError from board provider."""
    async def _test():
        sys_config = {
            "board_provider": "trello",
            "task_readfrom_state": "Sprint Backlog",
        }

        mock_provider = MagicMock()
        mock_provider.create_task = AsyncMock(
            side_effect=RuntimeError("Failed to create task: API error")
        )

        with patch(
            "agent.tools.create_task.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_task_tool(sys_config, "Sprint Backlog")
            result = await tool.ainvoke(
                {
                    "title": "Test Task",
                    "instructions": "Test instructions",
                }
            )

            assert "Failed to create task:" in result
            assert "API error" in result

    anyio.run(_test)


def test_create_task_tool_has_correct_metadata():
    """Test that the tool has correct name and description."""
    sys_config = {"board_provider": "trello"}

    tool = create_task_tool(sys_config, "To Do")

    assert tool.name == "create_task"
    assert "Creates a new task" in tool.description
    assert "implementation instructions" in tool.description


def test_create_task_tool_binds_sys_config_and_target_state():
    """Test that the factory function correctly binds sys_config and target state."""
    async def _test():
        sys_config_1 = {"board_provider": "trello"}
        sys_config_2 = {"board_provider": "trello"}

        mock_task_1 = BoardTask(
            id="task123",
            name="Task 1",
            description="Instructions 1",
            state_id="list_a",
            state_name="List A",
        )
        mock_task_1.url = "https://trello.com/c/task123"
        
        mock_task_2 = BoardTask(
            id="task456",
            name="Task 2",
            description="Instructions 2",
            state_id="list_b",
            state_name="List B",
        )
        mock_task_2.url = "https://trello.com/c/task456"

        mock_provider_1 = MagicMock()
        mock_provider_1.create_task = AsyncMock(return_value=mock_task_1)
        
        mock_provider_2 = MagicMock()
        mock_provider_2.create_task = AsyncMock(return_value=mock_task_2)

        with patch(
            "agent.tools.create_task.create_board_provider",
            side_effect=[mock_provider_1, mock_provider_2],
        ):
            tool_1 = create_task_tool(sys_config_1, "List A")
            tool_2 = create_task_tool(sys_config_2, "List B")

            # Call tool_1
            await tool_1.ainvoke({"title": "Task 1", "instructions": "Instructions 1"})

            # Verify it used List A
            call_args = mock_provider_1.create_task.call_args
            assert call_args[1]["state_name"] == "List A"
            assert call_args[1]["name"] == "Task 1"

            # Call tool_2
            await tool_2.ainvoke({"title": "Task 2", "instructions": "Instructions 2"})

            # Verify it used List B
            call_args = mock_provider_2.create_task.call_args
            assert call_args[1]["state_name"] == "List B"
            assert call_args[1]["name"] == "Task 2"

    anyio.run(_test)
