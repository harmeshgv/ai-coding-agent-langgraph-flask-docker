"""Unit tests for add_task_comment tool."""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
from langchain.tools import ToolRuntime

from app.core.taskboard.board_provider import BoardTask
from app.agent.tools.add_task_comment import add_task_comment

# Suppress Pydantic serialization warnings in tests
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")


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

        # Mock runtime with state and context
        mock_runtime = ToolRuntime(
            state={
                "board_task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict instead of None/Mock
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_1",
            store=None,
        )

        # Override context with our mock
        mock_runtime.context = mock_agent_settings

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock()

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ) as mock_create_board_provider:
            result = await add_task_comment.ainvoke(
                {
                    "comment": "This is a test comment",
                    "runtime": mock_runtime,
                }
            )

            assert "Successfully added comment to task 'Test Task'" in result
            assert "task123" in result
            assert "This is a test comment" in result
            mock_provider.add_comment.assert_called_once_with("task123", "This is a test comment")
            mock_create_board_provider.assert_called_once_with(mock_agent_settings)

    anyio.run(_test)


def test_add_task_comment_tool_handles_missing_task():
    """Test that the tool handles missing task in state gracefully."""

    async def _test():
        # Mock runtime without task in state
        mock_runtime = ToolRuntime(
            state={
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict instead of None/Mock
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_2",
            store=None,
        )

        result = await add_task_comment.ainvoke(
            {
                "comment": "This is a test comment",
                "runtime": mock_runtime,
            }
        )

        assert result == "Error: No current task found in state"

    anyio.run(_test)


def test_add_task_comment_tool_handles_none_agent_settings():
    """Test that the tool handles None agent settings gracefully."""

    async def _test():
        # Mock current task
        mock_task = BoardTask(
            id="task123",
            name="Test Task",
            description="Test description",
            state_id="list123",
            state_name="In Progress",
        )

        # Mock runtime with None context
        mock_runtime = ToolRuntime(
            state={
                "board_task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict, will be set to None in test
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_none_settings",
            store=None,
        )
        
        # Set context to None for this specific test
        mock_runtime.context = None

        result = await add_task_comment.ainvoke(
            {
                "comment": "This is a test comment",
                "runtime": mock_runtime,
            }
        )

        assert result == "Error: No agent settings found in runtime context"

    anyio.run(_test)


def test_add_task_comment_tool_handles_value_error():
    """Test that the tool handles ValueError from board provider gracefully."""

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

        # Mock runtime with state and context
        mock_runtime = ToolRuntime(
            state={
                "board_task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict instead of None/Mock
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_3",
            store=None,
        )

        # Override context with our mock
        mock_runtime.context = mock_agent_settings

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock(side_effect=ValueError("Task not found"))

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            result = await add_task_comment.ainvoke(
                {
                    "comment": "This is a test comment",
                    "runtime": mock_runtime,
                }
            )

            assert result == "Error: Task not found"

    anyio.run(_test)


def test_add_task_comment_tool_handles_runtime_error():
    """Test that the tool handles RuntimeError from board provider gracefully."""

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

        # Mock runtime with state and context
        mock_runtime = ToolRuntime(
            state={
                "board_task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict instead of None/Mock
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_4",
            store=None,
        )

        # Override context with our mock
        mock_runtime.context = mock_agent_settings

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock(side_effect=RuntimeError("API error: Failed to add comment"))

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            result = await add_task_comment.ainvoke(
                {
                    "comment": "This is a test comment",
                    "runtime": mock_runtime,
                }
            )

            assert result == "Failed to add comment: API error: Failed to add comment"

    anyio.run(_test)


def test_add_task_comment_tool_has_correct_metadata():
    """Test that the tool has correct metadata."""
    # Check that the tool has the correct name and description
    assert add_task_comment.name == "add_task_comment"
    assert "Adds a comment to the current task" in add_task_comment.description
    assert "board system" in add_task_comment.description


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

        # Mock runtime with state and context
        mock_runtime = ToolRuntime(
            state={
                "board_task": mock_task,
                "messages": [],
                "current_node": "analyst",
            },
            context={},  # Use empty dict instead of None/Mock
            config={},
            stream_writer=MagicMock(),
            tool_call_id="test_call_6",
            store=None,
        )

        # Override context with our mock
        mock_runtime.context = mock_agent_settings

        mock_provider = MagicMock()
        mock_provider.add_comment = AsyncMock()

        # Long comment (>100 chars)
        long_comment = "This is a very long comment that exceeds the 100 character limit for logging purposes and should be truncated in the log message"

        with patch(
            "app.agent.tools.add_task_comment.create_board_provider",
            return_value=mock_provider,
        ):
            with patch("app.agent.tools.add_task_comment.logger") as mock_logger:
                await add_task_comment.ainvoke(
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
