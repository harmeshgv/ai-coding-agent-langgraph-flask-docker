"""Unit tests for analyst node."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anyio
from cryptography.fernet import Fernet
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.nodes.analyst import create_analyst_node
from app.agent.state import AgentState, TaskType
from app.web import create_app


def test_analyst_node_creates_node():
    """Test that the factory function creates an analyst node."""
    mock_llm = MagicMock()
    mock_tools = [MagicMock()]

    node = create_analyst_node(mock_llm, mock_tools)

    assert callable(node)


def test_analyst_node_processes_non_coding_task_with_comment_tool():
    """Test that analyst node uses add_task_comment for non-coding tasks."""

    async def _test():
        # Create Flask app and run within app context
        app = create_app(Fernet.generate_key())
        
        with app.app_context():
            # Patch exist_plan at the module level before creating the node
            with patch("app.agent.nodes.analyst.exist_plan", return_value=False):
                mock_llm = MagicMock()
                
                # Mock tools including add_task_comment
                mock_add_comment_tool = MagicMock()
                mock_finish_tool = MagicMock()
                mock_tools = [mock_add_comment_tool, mock_finish_tool]

                # Create analyst node
                analyst_node = create_analyst_node(mock_llm, mock_tools)

                # Mock state for non-coding task
                mock_agent_task = MagicMock()
                state: AgentState = {
                    "messages": [
                        HumanMessage(content="Analyze the system architecture")
                    ],
                    "next_step": "analyst",
                    "board_task": MagicMock(),
                    "board_task_comments": [],
                    "agent_task": mock_agent_task,
                    "pr_review_message": None,
                    "task_type": TaskType.ANALYZING,
                    "task_skill_level": "senior",
                    "task_skill_level_reasoning": None,
                    "agent_stack": "backend",
                    "retry_count": 0,
                    "test_result": None,
                    "error_log": None,
                    "git_branch": "main",
                    "agent_skill_level": "senior",
                    "agent_summary": None,
                    "plan_content": None,
                    "plan_state": None,
                    "current_node": None,
                    "last_update": None,
                    "prompt": None,
                    "system_prompt": None,
                    "tech_stack": None,
                }

                # Mock LLM response with add_task_comment tool call
                mock_response = AIMessage(
                    content="I'll analyze the system architecture",
                    tool_calls=[
                        {
                            "name": "add_task_comment",
                            "args": {
                                "comment": "# System Architecture Analysis\n\n## Current State\nThe system uses a microservices architecture...",
                                "runtime": {"state": state}
                            },
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
                
                # Create a proper async mock for the LLM
                async def mock_ainvoke(messages):
                    return mock_response
                
                mock_llm.bind_tools.return_value.ainvoke = mock_ainvoke

                # Mock prompt loading and other dependencies
                with patch("app.agent.nodes.analyst.load_prompt"):
                    with patch("app.agent.nodes.base.filter_messages_for_llm", return_value=[]):
                        with patch("app.agent.nodes.analyst.record_finish_task_summary", return_value=(False, None)):
                            with patch("app.agent.nodes.analyst._get_plan_content_and_plan_state", return_value=(None, None)):
                                result = await analyst_node(state)

                                assert result["current_node"] == "analyst"
                                assert len(result["messages"]) >= 1
                                # Check that the response contains tool calls
                                assert any(hasattr(msg, 'tool_calls') and msg.tool_calls for msg in result["messages"])

    anyio.run(_test)


def test_analyst_node_processes_coding_task_with_plan_tool():
    """Test that analyst node uses write_plan for coding tasks."""

    async def _test():
        # Create Flask app and run within app context
        app = create_app(Fernet.generate_key())
        
        with app.app_context():
            # Patch exist_plan at the module level before creating the node
            with patch("app.agent.nodes.analyst.exist_plan", return_value=False):
                mock_llm = MagicMock()
                
                # Mock tools including write_plan
                mock_write_plan_tool = MagicMock()
                mock_finish_tool = MagicMock()
                mock_tools = [mock_write_plan_tool, mock_finish_tool]

                # Create analyst node
                analyst_node = create_analyst_node(mock_llm, mock_tools)

                # Mock state for coding task
                mock_agent_task = MagicMock()
                state: AgentState = {
                    "messages": [
                        HumanMessage(content="Implement a new feature")
                    ],
                    "next_step": "analyst",
                    "board_task": MagicMock(),
                    "board_task_comments": [],
                    "agent_task": mock_agent_task,
                    "pr_review_message": None,
                    "task_type": TaskType.CODING,
                    "task_skill_level": "senior",
                    "task_skill_level_reasoning": None,
                    "agent_stack": "backend",
                    "retry_count": 0,
                    "test_result": None,
                    "error_log": None,
                    "git_branch": "main",
                    "agent_skill_level": "senior",
                    "agent_summary": None,
                    "plan_content": None,
                    "plan_state": None,
                    "current_node": None,
                    "last_update": None,
                    "prompt": None,
                    "system_prompt": None,
                    "tech_stack": None,
                }

                # Mock LLM response with write_plan tool call
                mock_response = AIMessage(
                    content="I'll create an implementation plan",
                    tool_calls=[
                        {
                            "name": "write_plan",
                            "args": {
                                "plan_content": "# Implementation Plan\n\n## Affected Files\n- src/main/java/...\n\n## New Components\n- Service class...",
                            },
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
                
                # Create a proper async mock for the LLM
                async def mock_ainvoke(messages):
                    return mock_response
                
                mock_llm.bind_tools.return_value.ainvoke = mock_ainvoke

                # Mock prompt loading and other dependencies
                with patch("app.agent.nodes.analyst.load_prompt"):
                    with patch("app.agent.nodes.base.filter_messages_for_llm", return_value=[]):
                        with patch("app.agent.nodes.analyst.record_finish_task_summary", return_value=(False, None)):
                            with patch("app.agent.nodes.analyst._get_plan_content_and_plan_state", return_value=(None, None)):
                                result = await analyst_node(state)

                                assert result["current_node"] == "analyst"
                                assert len(result["messages"]) >= 1
                                # Check that the response contains tool calls
                                assert any(hasattr(msg, 'tool_calls') and msg.tool_calls for msg in result["messages"])

    anyio.run(_test)


def test_analyst_node_handles_finish_task_with_empty_summary():
    """Test that analyst node handles finish_task with empty summary for non-coding tasks."""

    async def _test():
        # Create Flask app and run within app context
        app = create_app(Fernet.generate_key())
        
        with app.app_context():
            # Patch exist_plan at the module level before creating the node
            with patch("app.agent.nodes.analyst.exist_plan", return_value=False):
                mock_llm = MagicMock()
                
                # Mock tools
                mock_add_comment_tool = MagicMock()
                mock_finish_tool = MagicMock()
                mock_tools = [mock_add_comment_tool, mock_finish_tool]

                # Create analyst node
                analyst_node = create_analyst_node(mock_llm, mock_tools)

                # Mock state for non-coding task
                mock_agent_task = MagicMock()
                state: AgentState = {
                    "messages": [
                        HumanMessage(content="Analyze the system architecture")
                    ],
                    "next_step": "analyst",
                    "board_task": MagicMock(),
                    "board_task_comments": [],
                    "agent_task": mock_agent_task,
                    "pr_review_message": None,
                    "task_type": TaskType.ANALYZING,
                    "task_skill_level": "senior",
                    "task_skill_level_reasoning": None,
                    "agent_stack": "backend",
                    "retry_count": 0,
                    "test_result": None,
                    "error_log": None,
                    "git_branch": "main",
                    "agent_skill_level": "senior",
                    "agent_summary": None,
                    "plan_content": None,
                    "plan_state": None,
                    "current_node": None,
                    "last_update": None,
                    "prompt": None,
                    "system_prompt": None,
                    "tech_stack": None,
                }

                # Mock LLM response with finish_task tool call and empty summary
                mock_response = AIMessage(
                    content="Analysis complete",
                    tool_calls=[
                        {
                            "name": "finish_task",
                            "args": {"summary": "Analysis complete."},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
                
                # Create a proper async mock for the LLM
                async def mock_ainvoke(messages):
                    return mock_response
                
                mock_llm.bind_tools.return_value.ainvoke = mock_ainvoke

                # Mock prompt loading and other dependencies
                with patch("app.agent.nodes.analyst.load_prompt"):
                    with patch("app.agent.nodes.base.filter_messages_for_llm", return_value=[]):
                        with patch("app.agent.nodes.analyst.record_finish_task_summary", return_value=(True, ["Analysis completed"])) as mock_record:
                            with patch("app.agent.nodes.analyst._get_plan_content_and_plan_state", return_value=(None, None)):
                                result = await analyst_node(state)

                                assert result["current_node"] == "analyst"
                                assert len(result["messages"]) >= 1
                                # Check that the response contains tool calls
                                assert any(hasattr(msg, 'tool_calls') and msg.tool_calls for msg in result["messages"])
                                
                                # Verify finish_task_summary was called exactly once (first successful tool call)
                                assert mock_record.call_count == 1

    anyio.run(_test)


def test_analyst_node_handles_invalid_response_with_retry():
    """Test that analyst node handles invalid responses and retries."""

    async def _test():
        # Create Flask app and run within app context
        app = create_app(Fernet.generate_key())
        
        with app.app_context():
            # Patch exist_plan at the module level before creating the node
            with patch("app.agent.nodes.analyst.exist_plan", return_value=False):
                mock_llm = MagicMock()
                mock_tools = [MagicMock()]

                # Create analyst node
                analyst_node = create_analyst_node(mock_llm, mock_tools)

                # Mock state
                mock_agent_task = MagicMock()
                state: AgentState = {
                    "messages": [
                        HumanMessage(content="Test task")
                    ],
                    "next_step": "analyst",
                    "board_task": MagicMock(),
                    "board_task_comments": [],
                    "agent_task": mock_agent_task,
                    "pr_review_message": None,
                    "task_type": TaskType.ANALYZING,
                    "task_skill_level": "senior",
                    "task_skill_level_reasoning": None,
                    "agent_stack": "backend",
                    "retry_count": 0,
                    "test_result": None,
                    "error_log": None,
                    "git_branch": "main",
                    "agent_skill_level": "senior",
                    "agent_summary": None,
                    "plan_content": None,
                    "plan_state": None,
                    "current_node": None,
                    "last_update": None,
                    "prompt": None,
                    "system_prompt": None,
                    "tech_stack": None,
                }

                # Mock LLM response without tool calls (invalid)
                mock_response = AIMessage(content="I'll think about this...")
                
                # Create a proper async mock for the LLM
                async def mock_ainvoke(messages):
                    return mock_response
                
                mock_llm.bind_tools.return_value.ainvoke = mock_ainvoke

                # Mock prompt loading and other dependencies
                with patch("app.agent.nodes.analyst.load_prompt"):
                    with patch("app.agent.nodes.base.filter_messages_for_llm", return_value=[]):
                        with patch("app.agent.nodes.analyst.record_finish_task_summary", return_value=(False, None)):
                            with patch("app.agent.nodes.analyst._get_plan_content_and_plan_state", return_value=(None, None)):
                                result = await analyst_node(state)

                                # Should have added error message and current_node should be analyst
                                assert result["current_node"] == "analyst"
                                # The node should handle the invalid response and create some output
                                assert len(result["messages"]) >= 1

    anyio.run(_test)


def test_analyst_node_sets_current_node_flag():
    """Test that analyst node sets current_node flag correctly."""

    async def _test():
        # Create Flask app and run within app context
        app = create_app(Fernet.generate_key())
        
        with app.app_context():
            # Patch exist_plan at the module level before creating the node
            with patch("app.agent.nodes.analyst.exist_plan", return_value=False):
                mock_llm = MagicMock()
                mock_tools = [MagicMock()]

                # Create analyst node
                analyst_node = create_analyst_node(mock_llm, mock_tools)

                # Mock state with current_node already set to "analyst"
                mock_agent_task = MagicMock()
                state: AgentState = {
                    "messages": [
                        HumanMessage(content="Test task")
                    ],
                    "next_step": "analyst",
                    "board_task": MagicMock(),
                    "board_task_comments": [],
                    "agent_task": mock_agent_task,
                    "pr_review_message": None,
                    "task_type": TaskType.ANALYZING,
                    "task_skill_level": "senior",
                    "task_skill_level_reasoning": None,
                    "agent_stack": "backend",
                    "retry_count": 0,
                    "test_result": None,
                    "error_log": None,
                    "git_branch": "main",
                    "agent_skill_level": "senior",
                    "agent_summary": None,
                    "plan_content": None,
                    "plan_state": None,
                    "current_node": "analyst",  # Already set
                    "last_update": None,
                    "prompt": None,
                    "system_prompt": None,
                    "tech_stack": None,
                }

                # Mock LLM response
                mock_response = AIMessage(
                    content="Analysis complete",
                    tool_calls=[
                        {
                            "name": "finish_task",
                            "args": {"summary": "Analysis complete."},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
                
                # Create a proper async mock for the LLM
                async def mock_ainvoke(messages):
                    return mock_response
                
                mock_llm.bind_tools.return_value.ainvoke = mock_ainvoke

                # Mock prompt loading and other dependencies
                with patch("app.agent.nodes.analyst.load_prompt"):
                    with patch("app.agent.nodes.base.filter_messages_for_llm", return_value=[]):
                        with patch("app.agent.nodes.analyst.record_finish_task_summary", return_value=(False, None)):
                            with patch("app.agent.nodes.analyst._get_plan_content_and_plan_state", return_value=(None, None)):
                                with patch("app.agent.nodes.base.sanitize_response", return_value=mock_response):
                                    # Mock logger to verify it doesn't log "--- ANALYST node ---" when already set
                                    with patch("app.agent.nodes.analyst.logger") as mock_logger:
                                        result = await analyst_node(state)

                                        # Verify logger.info was not called for node announcement
                                        mock_logger.info.assert_not_called()
                                        assert result["current_node"] == "analyst"

    anyio.run(_test)
