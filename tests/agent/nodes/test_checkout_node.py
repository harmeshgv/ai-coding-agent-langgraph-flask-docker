"""Tests for the checkout node."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.nodes import checkout as checkout_module
from app.agent.nodes.checkout import (
    _build_base_branch_name,
    _resolve_unique_branch_name,
    _slugify,
    checkout_task_branch,
)
from app.agent.state import TaskType
from app.core.localdb.models import AgentSettings
from app.core.taskboard.board_provider import ProviderTask


@pytest.fixture
def agent_settings():
    """Minimal AgentSettings for checkout tests."""
    return AgentSettings(github_repo_url="https://github.com/org/repo")


@pytest.fixture
def provider_task():
    return ProviderTask(
        id="abc123",
        name="Fix login bug",
        description="Users cannot log in",
        state_id="todo",
        state_name="To Do",
        url="https://example.com/task/abc123",
    )


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_string(self):
        assert _slugify("Fix Login Bug") == "fix-login-bug"

    def test_special_characters_replaced(self):
        assert _slugify("feat: add OAuth2.0 support!") == "feat-add-oauth2-0-support"

    def test_consecutive_separators_collapsed(self):
        assert _slugify("hello   world") == "hello-world"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("--hello--") == "hello"

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_none_returns_empty(self):
        assert _slugify(None) == ""

    def test_numbers_preserved(self):
        assert _slugify("task 42") == "task-42"


# ---------------------------------------------------------------------------
# _build_base_branch_name
# ---------------------------------------------------------------------------


class TestBuildBaseBranchName:
    def test_coding_task_uses_feature_prefix(self):
        name = _build_base_branch_name("abc123", "Add search", TaskType.CODING)
        assert name.startswith("agent/feature/")

    def test_bugfixing_task_uses_bugfix_prefix(self):
        name = _build_base_branch_name("abc123", "Fix crash", TaskType.BUGFIXING)
        assert name.startswith("agent/bugfix/")

    def test_unknown_task_type_uses_feature_prefix(self):
        name = _build_base_branch_name("abc123", "Some task", TaskType.UNKNOWN)
        assert name.startswith("agent/feature/")

    def test_analyzing_task_type_uses_feature_prefix(self):
        name = _build_base_branch_name("abc123", "Analyse perf", TaskType.ANALYZING)
        assert name.startswith("agent/feature/")

    def test_task_id_is_sanitized_and_truncated(self):
        name = _build_base_branch_name("ABC-123-XYZ", "My task", TaskType.CODING)
        assert "abc123xy" in name

    def test_long_task_name_is_truncated(self):
        long_name = "a" * 100
        name = _build_base_branch_name("id1", long_name, TaskType.CODING)
        slug_part = name.split("/")[-1].split("-", 1)[-1]
        assert len(slug_part) <= 48 + 1 + 8  # suffix + dash + short_id

    def test_empty_task_name_uses_update_fallback(self):
        name = _build_base_branch_name("id1", "", TaskType.CODING)
        assert "update" in name

    def test_empty_task_id_uses_task_fallback(self):
        name = _build_base_branch_name("", "My task", TaskType.CODING)
        assert "task" in name


# ---------------------------------------------------------------------------
# _resolve_unique_branch_name
# ---------------------------------------------------------------------------


class TestResolveUniqueBranchName:
    def test_no_conflict_returns_base(self):
        result = _resolve_unique_branch_name("agent/feature/abc-my-task", set())
        assert result == "agent/feature/abc-my-task"

    def test_conflict_appends_counter(self):
        existing = {"agent/feature/abc-my-task"}
        result = _resolve_unique_branch_name("agent/feature/abc-my-task", existing)
        assert result == "agent/feature/abc-my-task-1"

    def test_multiple_conflicts_increments_counter(self):
        existing = {
            "agent/feature/abc-my-task",
            "agent/feature/abc-my-task-1",
            "agent/feature/abc-my-task-2",
        }
        result = _resolve_unique_branch_name("agent/feature/abc-my-task", existing)
        assert result == "agent/feature/abc-my-task-3"


# ---------------------------------------------------------------------------
# checkout_task_branch
# ---------------------------------------------------------------------------


class TestCheckoutTaskBranch:
    @pytest.mark.asyncio
    async def test_non_coding_task_type_resets_and_returns_early(self, agent_settings):
        mock_repo = MagicMock()
        with (
            patch("app.agent.nodes.checkout.Repo", return_value=mock_repo),
            patch("app.agent.nodes.checkout.get_workspace", return_value="/workspace"),
        ):
            await checkout_task_branch("task-1", "Analyse perf", TaskType.ANALYZING, agent_settings)

        mock_repo.git.fetch.assert_called_once()
        mock_repo.git.reset.assert_called_once_with("--hard")

    @pytest.mark.asyncio
    async def test_analyzing_task_does_not_call_checkout(self, agent_settings):
        mock_repo = MagicMock()
        with (
            patch("app.agent.nodes.checkout.Repo", return_value=mock_repo),
            patch("app.agent.nodes.checkout.get_workspace", return_value="/workspace"),
            patch(
                "app.agent.nodes.checkout.get_existing_branch_for_task",
                new=AsyncMock(return_value="some-branch"),
            ) as mock_get_branch,
        ):
            await checkout_task_branch("task-1", "Analyse perf", TaskType.ANALYZING, agent_settings)

        mock_get_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_branch_is_checked_out(self, agent_settings):
        with (
            patch(
                "app.agent.nodes.checkout.get_existing_branch_for_task",
                new=AsyncMock(return_value="agent/feature/abc-my-task"),
            ),
            patch(
                "app.agent.nodes.checkout.checkout_branch"
            ) as mock_checkout,
            patch(
                "app.agent.nodes.checkout.get_current_branch", return_value="agent/feature/abc-my-task"
            ),
            patch("app.agent.nodes.checkout.get_workspace", return_value="/workspace"),
        ):
            await checkout_task_branch("task-1", "My task", TaskType.CODING, agent_settings)

        mock_checkout.assert_called_once_with(
            "https://github.com/org/repo", "agent/feature/abc-my-task", "/workspace"
        )

    @pytest.mark.asyncio
    async def test_no_existing_branch_creates_new_branch(self, agent_settings):
        with (
            patch(
                "app.agent.nodes.checkout.get_existing_branch_for_task",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.agent.nodes.checkout.checkout_branch_for_task",
                new=AsyncMock(),
            ) as mock_create,
            patch("app.agent.nodes.checkout.get_workspace", return_value="/workspace"),
        ):
            await checkout_task_branch("task-1", "My task", TaskType.CODING, agent_settings)

        mock_create.assert_called_once_with("task-1", "My task", TaskType.CODING, agent_settings)

    @pytest.mark.asyncio
    async def test_missing_github_repo_url_skips_checkout(self):
        settings = AgentSettings(github_repo_url=None)
        with (
            patch(
                "app.agent.nodes.checkout.get_existing_branch_for_task",
                new=AsyncMock(return_value="agent/feature/abc-my-task"),
            ),
            patch("app.agent.nodes.checkout.checkout_branch") as mock_checkout,
            patch(
                "app.agent.nodes.checkout.get_current_branch", return_value="agent/feature/abc-my-task"
            ),
            patch("app.agent.nodes.checkout.get_workspace", return_value="/workspace"),
        ):
            await checkout_task_branch("task-1", "My task", TaskType.CODING, settings)

        mock_checkout.assert_not_called()


# ---------------------------------------------------------------------------
# checkout_node (factory)
# ---------------------------------------------------------------------------


class TestCheckoutNode:
    @pytest.mark.asyncio
    async def test_raises_when_provider_task_missing(self, agent_settings):
        node = checkout_module.create_checkout_node(agent_settings)
        state = {"current_node": "checkout", "provider_task": None, "agent_task": None}

        with pytest.raises(ValueError, match="Missing task_id or task_name"):
            await node(state)

    @pytest.mark.asyncio
    async def test_returns_current_node_on_success(self, agent_settings, provider_task):
        node = checkout_module.create_checkout_node(agent_settings)
        state = {
            "current_node": "checkout",
            "provider_task": provider_task,
            "agent_task": None,
        }

        with patch(
            "app.agent.nodes.checkout.checkout_task_branch",
            new=AsyncMock(),
        ):
            result = await node(state)

        assert result == {"current_node": "checkout"}

    @pytest.mark.asyncio
    async def test_unknown_task_type_when_agent_task_is_none(self, agent_settings, provider_task):
        node = checkout_module.create_checkout_node(agent_settings)
        state = {
            "current_node": "checkout",
            "provider_task": provider_task,
            "agent_task": None,
        }

        with patch(
            "app.agent.nodes.checkout.checkout_task_branch",
            new=AsyncMock(),
        ) as mock_checkout:
            await node(state)

        _, _, called_task_type, _ = mock_checkout.call_args.args
        assert called_task_type == TaskType.CODING

    @pytest.mark.asyncio
    async def test_task_type_resolved_from_agent_task(self, agent_settings, provider_task):
        from app.core.localdb.models import AgentTask

        node = checkout_module.create_checkout_node(agent_settings)
        state = {
            "current_node": "checkout",
            "provider_task": provider_task,
            "agent_task": AgentTask(task_type="bugfixing"),
        }

        with patch(
            "app.agent.nodes.checkout.checkout_task_branch",
            new=AsyncMock(),
        ) as mock_checkout:
            await node(state)

        _, _, called_task_type, _ = mock_checkout.call_args.args
        assert called_task_type == TaskType.BUGFIXING
