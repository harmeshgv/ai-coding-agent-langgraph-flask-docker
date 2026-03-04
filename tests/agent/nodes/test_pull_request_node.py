"""Tests for the pull_request node."""

from unittest.mock import Mock

import pytest

from app.agent.models import AgentSummary
from app.agent.nodes import pull_request as pr_module
from app.core.localdb.models import AgentTask
from app.core.taskprovider.task_provider import ProviderTask


@pytest.fixture
def base_state():
    """Provide a default agent state structure."""
    return {
        "agent_summary": [AgentSummary(role="initial", summary="Initial summary")],
        "provider_task": ProviderTask(
            id="task-123",
            name="Improve testing",
            description="Ensure PR node is covered",
            state_id="todo",
            state_name="To Do",
            url="https://example.com/task/123",
        ),
    }


def _setup_success_path(monkeypatch):
    """Set default happy-path patches for git operations."""

    monkeypatch.setattr(pr_module, "git_has_changes", lambda *_, **__: True)
    monkeypatch.setattr(pr_module, "git_stage_all", lambda *_, **__: True)
    monkeypatch.setattr(pr_module, "git_commit", lambda *_, **__: True)
    monkeypatch.setattr(pr_module, "git_push", lambda *_, **__: (True, "pushed"))
    monkeypatch.setattr(pr_module, "_build_pr_inputs", lambda state: ("Title", "Body"))


def test_create_or_update_pr_success(monkeypatch, base_state):
    """Ensure successful PR creation appends a summary entry and stores PR info."""

    _setup_success_path(monkeypatch)
    pr_url = "https://github.com/foo/bar/pull/42"
    monkeypatch.setattr(
        pr_module,
        "create_or_update_pr",
        lambda title, body: (True, "done", pr_url),
    )

    update_mock = Mock()
    monkeypatch.setattr(pr_module, "update_db_task", update_mock)

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is True
    assert summaries[-1].role == "PR"
    assert summaries[-1].summary == f"Pull request available at\n\n {pr_url}"
    update_mock.assert_called_once_with(task_id="task-123", pr_number=42, pr_url=pr_url)


def test_create_or_update_pr_no_changes(monkeypatch, base_state):
    """Ensure failure path appends descriptive summary when no changes exist."""

    monkeypatch.setattr(pr_module, "git_has_changes", lambda *_, **__: False)

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1].role == "PR"
    assert summaries[-1].summary == "Pull request skipped: no changes detected"


def test_create_or_update_pr_push_failure(monkeypatch, base_state):
    """Git push failure should append summary describing the error."""

    _setup_success_path(monkeypatch)
    monkeypatch.setattr(pr_module, "git_push", lambda *_, **__: (False, "remote rejected"))

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1].role == "PR"
    assert summaries[-1].summary == "Pull request failed: git push failed (remote rejected)"


def test_create_or_update_pr_api_failure(monkeypatch, base_state):
    """GitHub API failure should record summary entry."""

    _setup_success_path(monkeypatch)
    monkeypatch.setattr(
        pr_module,
        "create_or_update_pr",
        lambda title, body: (False, "validation failed", None),
    )

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1].role == "PR"
    assert summaries[-1].summary == "Pull request creation/update failed: validation failed"


def test_create_or_update_pr_missing_url(monkeypatch, base_state):
    """Missing PR URL after success should add warning summary and return failure."""

    _setup_success_path(monkeypatch)
    monkeypatch.setattr(
        pr_module,
        "create_or_update_pr",
        lambda title, body: (True, "done", None),
    )

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1].role == "PR"
    assert summaries[-1].summary == "Pull request missing URL despite success"


class TestGenerateCommitMessage:
    """Unit tests for commit message generation logic."""

    def test_returns_default_when_no_summaries(self):
        state = {"agent_summary": []}

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert result == "fix: automated test-driven changes"

    def test_uses_chore_prefix_when_agent_task_is_none(self):
        state = {
            "agent_summary": [AgentSummary(role="coder", summary="Implement feature")],
            "agent_task": None,
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert result.startswith("chore: ")

    def test_multiline_coder_message_preserves_order(self):
        state = {
            "agent_summary": [
                AgentSummary(role="coder", summary="Implement persistence layer"),
                AgentSummary(role="coder", summary="Document storage contract"),
                AgentSummary(role="tester", summary="All tests green"),
            ],
            "agent_task": AgentTask(task_type="coding"),
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert (
            result == "feat: Implement persistence layer\n\n"
            "- Implement persistence layer\n- Document storage contract"
        )

    def test_skips_tester_and_uses_first_non_tester(self):
        state = {
            "agent_summary": [
                AgentSummary(role="tester", summary="Initial feedback"),
                AgentSummary(role="bugfixer", summary="Resolve race condition"),
                AgentSummary(role="bugfixer", summary="Add regression test"),
            ],
            "agent_task": AgentTask(task_type="bugfixing"),
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert (
            result == "fix: Resolve race condition\n\n"
            "- Resolve race condition\n- Add regression test"
        )

    def test_deduplicates_identical_coder_messages(self):
        state = {
            "agent_summary": [
                AgentSummary(role="coder", summary="Implement persistence layer"),
                AgentSummary(role="coder", summary="Implement persistence layer"),
                AgentSummary(role="coder", summary="Implement persistence layer"),
            ],
            "agent_task": AgentTask(task_type="coding"),
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert result == "feat: Implement persistence layer\n\n- Implement persistence layer"
