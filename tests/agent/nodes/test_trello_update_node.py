"""Unit tests for trello_update_node."""

from __future__ import annotations

from itertools import count
from unittest.mock import AsyncMock, patch

import anyio
from langchain_core.messages import AIMessage, ToolMessage

from agent.nodes.trello_update_node import (
    _build_agent_comments,
    _check_for_card_creation,
    create_trello_update_node,
    get_agent_result,
)
from agent.state import AgentState


_TOOL_CALL_COUNTER = count()


def _tool_call(name: str, args: dict | None = None) -> dict:
    """Helper to create tool call dictionaries."""
    return {
        "id": f"tool-call-{next(_TOOL_CALL_COUNTER)}",
        "name": name,
        "args": args or {},
    }


def test_check_for_card_creation_returns_false_when_no_card_created():
    """Test that _check_for_card_creation returns False when no card was created."""
    state: AgentState = {
        "messages": [
            AIMessage(content="", tool_calls=[_tool_call("finish_task")]),
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    card_created, card_info = _check_for_card_creation(state)

    assert card_created is False
    assert card_info is None


def test_check_for_card_creation_returns_true_when_issue_created():
    """Test that _check_for_card_creation detects successful card creation."""
    tool_response = (
        "Successfully created implementation issue: 'Add Division Support'\n"
        "Card URL: https://trello.com/c/abc123\n"
        "List: Sprint Backlog"
    )

    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "create_issue",
                        {
                            "title": "Add Division Support",
                            "instructions": "Implement division method",
                        },
                    )
                ],
            ),
            ToolMessage(content=tool_response, tool_call_id="tool-call-1"),
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    card_created, card_info = _check_for_card_creation(state)

    assert card_created is True
    assert card_info == tool_response


def test_check_for_card_creation_returns_false_when_card_creation_failed():
    """Test that _check_for_card_creation returns False when card creation failed."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "create_implementation_issue",
                        {"title": "Test", "instructions": "Test"},
                    )
                ],
            ),
            ToolMessage(
                content="Error: trello_readfrom_list not configured",
                tool_call_id="tool-call-1",
            ),
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    card_created, card_info = _check_for_card_creation(state)

    assert card_created is False
    assert card_info is None


def test_build_agent_comments_returns_default_when_no_entries():
    """Test that _build_agent_comments returns default comment when no entries."""
    state: AgentState = {
        "messages": [],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    comments = _build_agent_comments(state)

    assert len(comments) == 1
    assert "Task completed by AI Agent" in comments[0]


def test_build_agent_comments_includes_analysis_summary():
    """Test that _build_agent_comments includes the analysis summary."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "finish_task",
                        {
                            "summary": "Analysis complete. Found 3 issues.",
                            "agent_role": "analyst",
                        },
                    )
                ],
            ),
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    comments = _build_agent_comments(state)

    assert len(comments) == 1
    assert "**Agent Update:**" in comments[0]
    assert "Analysis complete. Found 3 issues." in comments[0]


def test_build_agent_comments_adds_second_comment_when_card_created():
    """Test that _build_agent_comments adds a second comment when card is created."""
    tool_response = (
        "Successfully created implementation issue: 'Fix Bug'\n"
        "Card URL: https://trello.com/c/xyz789\n"
        "List: To Do"
    )

    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "create_issue",
                        {"title": "Fix Bug", "instructions": "Fix the bug"},
                    )
                ],
            ),
            ToolMessage(content=tool_response, tool_call_id="tool-call-1"),
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "finish_task",
                        {
                            "summary": "Analysis complete.",
                            "agent_role": "analyst",
                        },
                    )
                ],
            ),
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    comments = _build_agent_comments(state)

    assert len(comments) == 2
    assert "**Agent Update:**" in comments[0]
    assert "Analysis complete." in comments[0]
    assert "**New Implementation Card Created:**" in comments[1]
    assert tool_response in comments[1]


def test_trello_update_node_adds_comments_and_moves_card():
    """Test that trello_update node adds comments and moves card."""
    async def _test():
        sys_config = {
            "trello_board_id": "board123",
            "trello_moveto_list": "Done",
        }

        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "finish_task",
                            {"summary": "Task done", "agent_role": "coder"},
                        )
                    ],
                ),
            ],
            "next_step": "",
            "agent_stack": "backend",
            "retry_count": 0,
            "test_result": None,
            "error_log": None,
            "trello_card_id": "card123",
            "trello_card_name": "Test Task",
            "trello_list_id": "list123",
            "git_branch": None,
            "agent_skill_level": None,
            "task_skill_level": None,
            "agent_summary": None,
        }

        with patch(
            "agent.nodes.trello_update_node.add_comment_to_trello_card",
            new_callable=AsyncMock,
        ) as mock_add_comment, patch(
            "agent.nodes.trello_update_node.move_trello_card_to_named_list",
            new_callable=AsyncMock,
        ) as mock_move_card:
            mock_move_card.return_value = "list456"

            trello_update = create_trello_update_node(sys_config)
            result = await trello_update(state)

            # Verify comment was added
            mock_add_comment.assert_called_once()
            call_args = mock_add_comment.call_args
            assert call_args[0][0] == "card123"
            assert "Task done" in call_args[0][1]

            # Verify card was moved
            mock_move_card.assert_called_once_with("card123", "Done", sys_config)

            # Verify result
            assert result["trello_list_id"] == "list456"

    anyio.run(_test)


def test_trello_update_node_handles_missing_card_id():
    """Test that trello_update node handles missing card ID gracefully."""
    async def _test():
        sys_config = {"trello_board_id": "board123"}

        state: AgentState = {
            "messages": [],
            "next_step": "",
            "agent_stack": "backend",
            "retry_count": 0,
            "test_result": None,
            "error_log": None,
            "trello_card_id": None,
            "trello_card_name": None,
            "trello_list_id": None,
            "git_branch": None,
            "agent_skill_level": None,
            "task_skill_level": None,
            "agent_summary": None,
        }

        trello_update = create_trello_update_node(sys_config)
        result = await trello_update(state)

        assert result == {}

    anyio.run(_test)


def test_trello_update_node_handles_comment_failure():
    """Test that trello_update node continues when adding comment fails."""
    async def _test():
        sys_config = {
            "trello_board_id": "board123",
            "trello_moveto_list": "Done",
        }

        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "finish_task",
                            {"summary": "Task done", "agent_role": "coder"},
                        )
                    ],
                ),
            ],
            "next_step": "",
            "agent_stack": "backend",
            "retry_count": 0,
            "test_result": None,
            "error_log": None,
            "trello_card_id": "card123",
            "trello_card_name": "Test Task",
            "trello_list_id": "list123",
            "git_branch": None,
            "agent_skill_level": None,
            "task_skill_level": None,
            "agent_summary": None,
        }

        with patch(
            "agent.nodes.trello_update_node.add_comment_to_trello_card",
            new_callable=AsyncMock,
        ) as mock_add_comment, patch(
            "agent.nodes.trello_update_node.move_trello_card_to_named_list",
            new_callable=AsyncMock,
        ) as mock_move_card:
            mock_add_comment.side_effect = Exception("API Error")
            mock_move_card.return_value = "list456"

            trello_update = create_trello_update_node(sys_config)
            result = await trello_update(state)

            # Should still move card even if comment fails
            mock_move_card.assert_called_once_with("card123", "Done", sys_config)
            assert result["trello_list_id"] == "list456"

    anyio.run(_test)


def test_trello_update_node_handles_move_value_error():
    """Test that trello_update node handles ValueError when moving card."""
    async def _test():
        sys_config = {
            "trello_board_id": "board123",
            "trello_moveto_list": "Invalid List",
        }

        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "finish_task",
                            {"summary": "Task done", "agent_role": "coder"},
                        )
                    ],
                ),
            ],
            "next_step": "",
            "agent_stack": "backend",
            "retry_count": 0,
            "test_result": None,
            "error_log": None,
            "trello_card_id": "card123",
            "trello_card_name": "Test Task",
            "trello_list_id": "list123",
            "git_branch": None,
            "agent_skill_level": None,
            "task_skill_level": None,
            "agent_summary": None,
        }

        with patch(
            "agent.nodes.trello_update_node.add_comment_to_trello_card",
            new_callable=AsyncMock,
        ), patch(
            "agent.nodes.trello_update_node.move_trello_card_to_named_list",
            new_callable=AsyncMock,
        ) as mock_move_card:
            mock_move_card.side_effect = ValueError("List not found")

            trello_update = create_trello_update_node(sys_config)
            result = await trello_update(state)

            # Should return None for card_id on ValueError
            assert result["trello_card_id"] is None

    anyio.run(_test)


def test_trello_update_node_handles_move_generic_error():
    """Test that trello_update node handles generic Exception when moving card."""
    async def _test():
        sys_config = {
            "trello_board_id": "board123",
            "trello_moveto_list": "Done",
        }

        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "finish_task",
                            {"summary": "Task done", "agent_role": "coder"},
                        )
                    ],
                ),
            ],
            "next_step": "",
            "agent_stack": "backend",
            "retry_count": 0,
            "test_result": None,
            "error_log": None,
            "trello_card_id": "card123",
            "trello_card_name": "Test Task",
            "trello_list_id": "list123",
            "git_branch": None,
            "agent_skill_level": None,
            "task_skill_level": None,
            "agent_summary": None,
        }

        with patch(
            "agent.nodes.trello_update_node.add_comment_to_trello_card",
            new_callable=AsyncMock,
        ), patch(
            "agent.nodes.trello_update_node.move_trello_card_to_named_list",
            new_callable=AsyncMock,
        ) as mock_move_card:
            mock_move_card.side_effect = RuntimeError("Network error")

            trello_update = create_trello_update_node(sys_config)
            result = await trello_update(state)

            # Should return None for card_id on generic Exception
            assert result["trello_card_id"] is None

    anyio.run(_test)


def test_check_for_card_creation_with_non_adjacent_tool_message():
    """Test that _check_for_card_creation handles non-adjacent ToolMessage."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "create_implementation_card",
                        {"title": "Test", "instructions": "Test"},
                    )
                ],
            ),
            AIMessage(content="Thinking..."),  # Non-ToolMessage in between
        ],
        "next_step": "",
        "agent_stack": "backend",
        "retry_count": 0,
        "test_result": None,
        "error_log": None,
        "trello_card_id": None,
        "trello_card_name": None,
        "trello_list_id": None,
        "git_branch": None,
        "agent_skill_level": None,
        "task_skill_level": None,
        "agent_summary": None,
    }

    card_created, card_info = _check_for_card_creation(state)

    # Should return False when ToolMessage is not immediately after AIMessage
    assert card_created is False
    assert card_info is None


def test_get_agent_result_returns_summary_from_finish_task():
    """Test that get_agent_result extracts summary from finish_task tool call."""
    messages = [
        AIMessage(content="Working on it..."),
        AIMessage(
            content="",
            tool_calls=[
                _tool_call("finish_task", {"summary": "Task completed successfully"})
            ],
        ),
    ]

    result = get_agent_result(messages)

    assert result == "Task completed successfully"


def test_get_agent_result_returns_default_when_no_finish_task():
    """Test that get_agent_result returns default when no finish_task found."""
    messages = [
        AIMessage(content="Working on it..."),
        AIMessage(content="", tool_calls=[_tool_call("thinking", {})]),
    ]

    result = get_agent_result(messages)

    assert result == "Task completed by AI Agent."


def test_get_agent_result_returns_default_when_no_summary_in_finish_task():
    """Test that get_agent_result returns default when finish_task has no summary."""
    messages = [
        AIMessage(content="", tool_calls=[_tool_call("finish_task", {})]),
    ]

    result = get_agent_result(messages)

    assert result == "Task completed by AI Agent."


def test_get_agent_result_searches_backward_through_messages():
    """Test that get_agent_result searches backward and finds most recent finish_task."""
    messages = [
        AIMessage(
            content="",
            tool_calls=[_tool_call("finish_task", {"summary": "First attempt"})],
        ),
        AIMessage(content="Continuing work..."),
        AIMessage(
            content="",
            tool_calls=[_tool_call("finish_task", {"summary": "Final result"})],
        ),
    ]

    result = get_agent_result(messages)

    # Should return the most recent (last) finish_task summary
    assert result == "Final result"
