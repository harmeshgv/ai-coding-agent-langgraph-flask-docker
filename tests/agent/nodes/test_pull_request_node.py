"""Tests for the pull_request node."""

from unittest.mock import Mock

import pytest

from app.agent.nodes import pull_request as pr_module


@pytest.fixture
def base_state():
    """Provide a default agent state structure."""
    return {
        "agent_summary": ["Initial summary"],
        "task_id": "task-123",
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
    assert summaries[-1] == f"**[Pr]** Pull request available at\n\n {pr_url}"
    update_mock.assert_called_once_with(task_id="task-123", pr_number=42, pr_url=pr_url)


def test_create_or_update_pr_no_changes(monkeypatch, base_state):
    """Ensure failure path appends descriptive summary when no changes exist."""

    monkeypatch.setattr(pr_module, "git_has_changes", lambda *_, **__: False)

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1] == "**[Pr]** Pull request skipped: no changes detected"


def test_create_or_update_pr_push_failure(monkeypatch, base_state):
    """Git push failure should append summary describing the error."""

    _setup_success_path(monkeypatch)
    monkeypatch.setattr(pr_module, "git_push", lambda *_, **__: (False, "remote rejected"))

    success, summaries = pr_module._create_or_update_pr(base_state.copy())  # pylint: disable=protected-access

    assert success is False
    assert summaries[-1] == "**[Pr]** Pull request failed: git push failed (remote rejected)"


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
    assert summaries[-1] == "**[Pr]** Pull request creation/update failed: validation failed"


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
    assert summaries[-1] == "**[Pr]** Pull request missing URL despite success"


class TestGenerateCommitMessage:
    """Unit tests for commit message generation logic."""

    def test_returns_default_when_no_summaries(self):
        state = {"agent_summary": []}

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert result == "fix: automated test-driven changes"

    def test_multiline_coder_message_preserves_order(self):
        state = {
            "agent_summary": [
                "**[Coder]** Implement persistence layer",
                "**[Coder]** Document storage contract",
                "**[Tester]** All tests green",
            ]
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert (
            result
            == "feat: Implement persistence layer\n\n"
            "- Implement persistence layer\n- Document storage contract"
        )

    def test_skips_tester_and_uses_first_non_tester(self):
        state = {
            "agent_summary": [
                "**[Tester]** Initial feedback",
                "**[Bugfixer]** Resolve race condition",
                "**[Bugfixer]** Add regression test",
            ]
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert (
            result
            == "fix: Resolve race condition\n\n"
            "- Resolve race condition\n- Add regression test"
        )

    def test_deduplicates_identical_coder_messages(self):
        state = {
            "agent_summary": [
                "**[Coder]** Implement persistence layer",
                "**[Coder]** Implement persistence layer",
                "**[Coder]** Implement persistence layer",
            ]
        }

        result = pr_module._generate_commit_message(state)  # pylint: disable=protected-access

        assert result == "feat: Implement persistence layer\n\n- Implement persistence layer"
