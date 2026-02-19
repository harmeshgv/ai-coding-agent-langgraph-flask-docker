"""Unit tests for add_task_comment tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
from langchain.tools import ToolRuntime

from app.core.taskboard.board_provider import BoardTask
from app.agent.tools.add_task_comment import create_add_task_comment_tool


def test_add_task_comment_tool_adds_comment_successfully():
    """Test that the tool adds a comment successfully with valid task."""

    async def _test():
        # Mock AgentSettings
        mock_agent_settings = MagicMock()
        
        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )
        mock_task.url = "https://trello.com/c/task123"

        # Mock runtime with state
        mock_runtime = ToolRuntime(
            state={
                "task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_1",
            store=None,
        )

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock()

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_add_task_comment_tool(mock_agent_settings)
            result = await tool.ainvoke(
                {
                    "comment": "This is a test comment",
                    "runtime": mock_runtime,
                }
            )

            mock_provider.add_comment.assert_called_once_with("task123", "This is a test comment")

            assert "Successfully added comment to task 'Test Task'" in result
            assert "ID: task123" in result
            assert "This is a test comment" in result

    anyio.run(_test)


def test_add_task_comment_tool_handles_missing_task():
    """Test that the tool handles missing task in state."""

    async def _test():
        mock_agent_settings = MagicMock()
        
        # Mock runtime with no task
        mock_runtime = ToolRuntime(
            state={
                "task": None,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_2",
            store=None,
        )

        tool = create_add_task_comment_tool(mock_agent_settings)
        result = await tool.ainvoke(
            {
                "comment": "Test comment",
                "runtime": mock_runtime,
            }
        )

        assert "Error: No current task found in state" in result

    anyio.run(_test)


def test_add_task_comment_tool_handles_value_error():
    """Test that the tool handles ValueError from board provider."""

    async def _test():
        mock_agent_settings = MagicMock()
        
        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )

        # Mock runtime with state
        mock_runtime = ToolRuntime(
            state={
                "task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_3",
            store=None,
        )

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock(
            side_effect=ValueError("Task not found")
        )

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_add_task_comment_tool(mock_agent_settings)
            result = await tool.ainvoke(
                {
                    "comment": "Test comment",
                    "runtime": mock_runtime,
                }
            )

            assert "Error:" in result
            assert "Task not found" in result

    anyio.run(_test)


def test_add_task_comment_tool_handles_runtime_error():
    """Test that the tool handles RuntimeError from board provider."""

    async def _test():
        mock_agent_settings = MagicMock()
        
        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )

        # Mock runtime with state
        mock_runtime = ToolRuntime(
            state={
                "task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_4",
            store=None,
        )

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock(
            side_effect=RuntimeError("API error: Failed to add comment")
        )

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            tool = create_add_task_comment_tool(mock_agent_settings)
            result = await tool.ainvoke(
                {
                    "comment": "Test comment",
                    "runtime": mock_runtime,
                }
            )

            assert "Failed to add comment:" in result
            assert "API error: Failed to add comment" in result

    anyio.run(_test)


def test_add_task_comment_tool_has_correct_metadata():
    """Test that the tool has correct name and description."""
    mock_agent_settings = MagicMock()

    tool = create_add_task_comment_tool(mock_agent_settings)

    assert tool.name == "add_task_comment"
    assert "Adds a comment to the current task" in tool.description
    assert "board system" in tool.description


def test_add_task_comment_tool_binds_agent_settings():
    """Test that the factory function correctly binds agent settings."""

    async def _test():
        # Mock different AgentSettings
        mock_agent_settings_1 = MagicMock()
        mock_agent_settings_2 = MagicMock()

        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )

        # Mock runtime with state
        mock_runtime = ToolRuntime(
            state={
                "task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_5",
            store=None,
        )

        mock_provider_1 = MagicMock()
        mock_provider_1.add_comment = AsyncMock()

        mock_provider_2 = MagicMock()
        mock_provider_2.add_comment = AsyncMock()

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            side_effect=[mock_provider_1, mock_provider_2],
        ):
            tool_1 = create_add_task_comment_tool(mock_agent_settings_1)
            tool_2 = create_add_task_comment_tool(mock_agent_settings_2)

            # Call tool_1
            await tool_1.ainvoke({"comment": "Comment 1", "runtime": mock_runtime})

            # Verify it used the first agent settings
            mock_provider_1.add_comment.assert_called_once_with("task123", "Comment 1")

            # Call tool_2
            await tool_2.ainvoke({"comment": "Comment 2", "runtime": mock_runtime})

            # Verify it used the second agent settings
            mock_provider_2.add_comment.assert_called_once_with("task123", "Comment 2")

    anyio.run(_test)


def test_add_task_comment_tool_logs_long_comment():
    """Test that the tool logs truncated version of long comments."""

    async def _test():
        mock_agent_settings = MagicMock()
        
        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )

        # Mock runtime with state
        mock_runtime = ToolRuntime(
            state={
                "task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_6",
            store=None,
        )

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock()

        # Long comment (>100 chars)
        long_comment = "This is a very long comment that exceeds the 100 character limit for logging purposes and should be truncated in the log message"

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            with patch("app.agent.tools.add_task_comment.logger") as mock_logger:
                tool = create_add_task_comment_tool(mock_agent_settings)
                await tool.ainvoke(
                    {
                        "comment": long_comment,
                        "runtime": mock_runtime,
                    }
                )

                # Verify the comment was passed in full to the provider
                mock_provider.add_comment.assert_called_once_with("task123", long_comment)

                # Verify the logger was called with truncated comment
                mock_logger.info.assert_called_once()
                log_call_args = mock_logger.info.call_args[0]
                assert "..." in log_call_args[3]  # The truncated comment
                assert len(log_call_args[3]) <= 103  # 100 chars + "..."

    anyio.run(_test)
