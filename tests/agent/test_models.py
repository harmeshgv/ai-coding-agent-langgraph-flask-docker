"""Unit tests for agent.models."""

import pytest

from app.agent.models import AgentSummary


def test_agent_summary_creation():
    """Test creating an AgentSummary instance."""
    summary = AgentSummary(role="coder", summary="Implemented feature X")
    assert summary.role == "coder"
    assert summary.summary == "Implemented feature X"


def test_agent_summary_strips_whitespace():
    """Test that AgentSummary strips whitespace from role and summary."""
    summary = AgentSummary(role="  coder  ", summary="  Implemented feature X  ")
    assert summary.role == "coder"
    assert summary.summary == "Implemented feature X"


def test_agent_summary_to_markdown():
    """Test the to_markdown method."""
    summary = AgentSummary(role="coder", summary="Implemented feature X")
    assert summary.to_markdown() == "**[Coder]** Implemented feature X"


def test_agent_summary_to_markdown_capitalizes_role():
    """Test that to_markdown capitalizes the role."""
    summary = AgentSummary(role="tester", summary="All tests passed")
    assert summary.to_markdown() == "**[Tester]** All tests passed"


def test_agent_summary_invalid_role_type():
    """Test that AgentSummary raises TypeError for invalid role type."""
    with pytest.raises(TypeError, match="role must be a string"):
        AgentSummary(role=123, summary="Test summary")


def test_agent_summary_invalid_summary_type():
    """Test that AgentSummary raises TypeError for invalid summary type."""
    with pytest.raises(TypeError, match="summary must be a string"):
        AgentSummary(role="coder", summary=123)


def test_agent_summary_equality():
    """Test that two AgentSummary instances with same values are equal."""
    summary1 = AgentSummary(role="coder", summary="Implemented feature X")
    summary2 = AgentSummary(role="coder", summary="Implemented feature X")
    assert summary1.role == summary2.role
    assert summary1.summary == summary2.summary
