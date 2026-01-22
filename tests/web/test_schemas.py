"""Tests for web layer Pydantic schemas."""

from __future__ import annotations

from app.web.schemas.settings_schema import (
    GitHubConfigSchema,
    JiraConfigSchema,
    LLMConfigSchema,
    SettingsFormSchema,
    TrelloConfigSchema,
)


class TestTrelloConfigSchema:
    """Tests for TrelloConfigSchema validation."""

    def test_empty_strings_converted_to_none(self):
        """Empty strings should be converted to None."""
        schema = TrelloConfigSchema(
            api_key="",
            api_token="",
            board_id="",
        )
        assert schema.api_key is None
        assert schema.api_token is None
        assert schema.board_id is None

    def test_valid_values_preserved(self):
        """Valid string values should be preserved."""
        schema = TrelloConfigSchema(
            api_key="test-key",
            api_token="test-token",
            board_id="board-123",
            backlog_list="list-1",
            readfrom_list="list-2",
            progress_list="list-3",
            moveto_list="list-4",
        )
        assert schema.api_key == "test-key"
        assert schema.api_token == "test-token"
        assert schema.board_id == "board-123"
        assert schema.backlog_list == "list-1"

    def test_default_base_url(self):
        """Base URL should default to Trello API."""
        schema = TrelloConfigSchema()
        assert schema.base_url == "https://api.trello.com/1"


class TestLLMConfigSchema:
    """Tests for LLMConfigSchema validation."""

    def test_default_provider(self):
        """Provider should default to mistral."""
        schema = LLMConfigSchema()
        assert schema.provider == "mistral"

    def test_empty_provider_defaults_to_mistral(self):
        """Empty provider string should default to mistral."""
        schema = LLMConfigSchema(provider="")
        assert schema.provider == "mistral"

    def test_valid_provider_preserved(self):
        """Valid provider should be preserved."""
        schema = LLMConfigSchema(provider="openai")
        assert schema.provider == "openai"

    def test_empty_model_strings_to_none(self):
        """Empty model strings should be converted to None."""
        schema = LLMConfigSchema(
            model_large="",
            model_small="",
            temperature="",
        )
        assert schema.model_large is None
        assert schema.model_small is None
        assert schema.temperature is None


class TestSettingsFormSchema:
    """Tests for SettingsFormSchema validation."""

    def test_default_values(self):
        """Schema should have sensible defaults."""
        schema = SettingsFormSchema()
        assert schema.task_system_type == "TRELLO"
        assert schema.polling_interval_seconds == 60
        assert schema.repo_type == "GITHUB"
        assert schema.is_active is False

    def test_polling_interval_parsing(self):
        """Polling interval should be parsed from string."""
        schema = SettingsFormSchema(polling_interval_seconds="120")
        assert schema.polling_interval_seconds == 120

    def test_polling_interval_invalid_defaults_to_60(self):
        """Invalid polling interval should default to 60."""
        schema = SettingsFormSchema(polling_interval_seconds="invalid")
        assert schema.polling_interval_seconds == 60

    def test_polling_interval_empty_defaults_to_60(self):
        """Empty polling interval should default to 60."""
        schema = SettingsFormSchema(polling_interval_seconds="")
        assert schema.polling_interval_seconds == 60

    def test_is_active_from_string(self):
        """is_active should parse various truthy strings."""
        assert SettingsFormSchema(is_active="true").is_active is True
        assert SettingsFormSchema(is_active="1").is_active is True
        assert SettingsFormSchema(is_active="on").is_active is True
        assert SettingsFormSchema(is_active="yes").is_active is True
        assert SettingsFormSchema(is_active="false").is_active is False
        assert SettingsFormSchema(is_active="0").is_active is False

    def test_is_active_from_bool(self):
        """is_active should accept boolean values."""
        assert SettingsFormSchema(is_active=True).is_active is True
        assert SettingsFormSchema(is_active=False).is_active is False

    def test_nested_trello_config(self):
        """Schema should accept nested Trello config."""
        trello = TrelloConfigSchema(api_key="key", board_id="board")
        schema = SettingsFormSchema(trello_config=trello)
        assert schema.trello_config is not None
        assert schema.trello_config.api_key == "key"

    def test_nested_llm_config_defaults(self):
        """LLM config should have defaults when not provided."""
        schema = SettingsFormSchema()
        assert schema.llm_config is not None
        assert schema.llm_config.provider == "mistral"


class TestJiraConfigSchema:
    """Tests for JiraConfigSchema validation."""

    def test_empty_strings_converted_to_none(self):
        """Empty strings should be converted to None."""
        schema = JiraConfigSchema(
            username="",
            api_token="",
            jql_query="",
        )
        assert schema.username is None
        assert schema.api_token is None
        assert schema.jql_query is None

    def test_valid_values_preserved(self):
        """Valid string values should be preserved."""
        schema = JiraConfigSchema(
            username="user@example.com",
            api_token="token-123",
            jql_query="project = TEST",
        )
        assert schema.username == "user@example.com"
        assert schema.api_token == "token-123"
        assert schema.jql_query == "project = TEST"


class TestGitHubConfigSchema:
    """Tests for GitHubConfigSchema validation."""

    def test_empty_strings_converted_to_none(self):
        """Empty strings should be converted to None."""
        schema = GitHubConfigSchema(
            project_owner="",
            board_id="",
            api_token="",
        )
        assert schema.project_owner is None
        assert schema.board_id is None
        assert schema.api_token is None

    def test_empty_project_number_converted_to_none(self):
        """Empty project number should be converted to None."""
        schema = GitHubConfigSchema(project_number="")
        assert schema.project_number == ""

    def test_project_number_parsed_from_string(self):
        """Project number should be parsed from string."""
        schema = GitHubConfigSchema(project_number="42")
        assert schema.project_number == "42"

    def test_valid_values_preserved(self):
        """Valid values should be preserved."""
        schema = GitHubConfigSchema(
            project_owner="octocat",
            project_number="1",
            board_id="PVT_kwDOxxxxxx",
            api_token="ghp_test_token",
            backlog_list="Backlog",
            readfrom_list="Todo",
            progress_list="In Progress",
            moveto_list="Done",
        )
        assert schema.project_owner == "octocat"
        assert schema.project_number == "1"
        assert schema.board_id == "PVT_kwDOxxxxxx"
        assert schema.api_token == "ghp_test_token"
        assert schema.backlog_list == "Backlog"
        assert schema.readfrom_list == "Todo"
        assert schema.progress_list == "In Progress"
        assert schema.moveto_list == "Done"

    def test_default_base_url(self):
        """Base URL should default to GitHub API."""
        schema = GitHubConfigSchema()
        assert schema.base_url == "https://api.github.com"

    def test_custom_base_url_for_enterprise(self):
        """Custom base URL should be accepted for GitHub Enterprise."""
        schema = GitHubConfigSchema(base_url="https://github.mycompany.com/api")
        assert schema.base_url == "https://github.mycompany.com/api"


class TestSettingsFormSchemaWithGitHub:
    """Tests for SettingsFormSchema with GitHub configuration."""

    def test_nested_github_config(self):
        """Schema should accept nested GitHub config."""
        github = GitHubConfigSchema(project_owner="octocat", project_number="1")
        schema = SettingsFormSchema(
            task_system_type="GITHUB",
            github_config=github,
        )
        assert schema.github_config is not None
        assert schema.github_config.project_owner == "octocat"
        assert schema.github_config.project_number == "1"

    def test_github_task_system_type(self):
        """Schema should accept GITHUB as task system type."""
        schema = SettingsFormSchema(task_system_type="GITHUB")
        assert schema.task_system_type == "GITHUB"
