"""Tests for web layer mappers."""

from __future__ import annotations

from app.core.models import AgentSettings, TaskSystem
from app.web.mappers.config_mapper import ConfigMapper
from app.web.schemas.settings_schema import (
    GitHubConfigSchema,
    LLMConfigSchema,
    SettingsFormSchema,
    TrelloConfigSchema,
)


class TestConfigMapperSchemaToModel:
    """Tests for ConfigMapper.schema_to_model."""

    def test_applies_basic_fields(self, app):
        """Basic fields should be applied to model."""
        schema = SettingsFormSchema(
            task_system_type="TRELLO",
            agent_skill_level="senior",
            polling_interval_seconds=120,
            repo_type="GITHUB",
            github_repo_url="https://github.com/test/repo.git",
            is_active=True,
        )
        settings = AgentSettings()

        result = ConfigMapper.schema_to_model(schema, settings)

        assert result.task_system_type == "TRELLO"
        assert result.agent_skill_level == "senior"
        assert result.polling_interval_seconds == 120
        assert result.repo_type == "GITHUB"
        assert result.github_repo_url == "https://github.com/test/repo.git"
        assert result.is_active is True

    def test_applies_llm_config(self, app):
        """LLM config should be applied to model."""
        llm_config = LLMConfigSchema(
            provider="openai",
            model_large="gpt-4",
            model_small="gpt-3.5-turbo",
            temperature="0.7",
        )
        schema = SettingsFormSchema(llm_config=llm_config)
        settings = AgentSettings()

        result = ConfigMapper.schema_to_model(schema, settings)

        assert result.llm_provider == "openai"
        assert result.llm_model_large == "gpt-4"
        assert result.llm_model_small == "gpt-3.5-turbo"
        assert result.llm_temperature == "0.7"

    def test_applies_trello_config(self, app):
        """Trello config should be applied to model and task_system."""
        trello_config = TrelloConfigSchema(
            api_key="test-key",
            api_token="test-token",
            base_url="https://api.trello.com/1",
            board_id="board-123",
            backlog_list="list-1",
            readfrom_list="list-2",
            progress_list="list-3",
            moveto_list="list-4",
        )
        schema = SettingsFormSchema(
            task_system_type="TRELLO",
            trello_config=trello_config,
        )
        settings = AgentSettings()

        result = ConfigMapper.schema_to_model(schema, settings)

        trello_ts = result.get_task_system("trello")
        assert trello_ts is not None
        assert trello_ts.backlog_state == "list-1"
        assert trello_ts.readfrom_state == "list-2"
        assert trello_ts.in_progress_state == "list-3"
        assert trello_ts.moveto_state == "list-4"
        assert trello_ts.api_key == "test-key"
        assert trello_ts.token == "test-token"
        assert trello_ts.board_id == "board-123"

    def test_creates_task_system_if_missing(self, app):
        """TaskSystem should be created if not present."""
        trello_config = TrelloConfigSchema(api_key="key")
        schema = SettingsFormSchema(
            task_system_type="TRELLO",
            trello_config=trello_config,
        )
        settings = AgentSettings()
        assert len(settings.task_systems) == 0

        result = ConfigMapper.schema_to_model(schema, settings)

        trello_ts = result.get_task_system("trello")
        assert trello_ts is not None
        assert trello_ts.board_provider == "trello"

    def test_reuses_existing_task_system(self, app):
        """Existing TaskSystem should be reused."""
        existing_task_system = TaskSystem(
            task_system_type="TRELLO",
            board_provider="trello",
            board_id="old-board",
        )
        trello_config = TrelloConfigSchema(board_id="new-board")
        schema = SettingsFormSchema(
            task_system_type="TRELLO",
            trello_config=trello_config,
        )
        settings = AgentSettings()
        settings.task_systems.append(existing_task_system)

        result = ConfigMapper.schema_to_model(schema, settings)

        trello_ts = result.get_task_system("trello")
        assert trello_ts is existing_task_system
        assert trello_ts.board_id == "new-board"


class TestConfigMapperModelToFormData:
    """Tests for ConfigMapper.model_to_form_data."""

    def test_extracts_basic_fields(self, app):
        """Basic fields should be extracted from model."""
        config = AgentSettings(
            agent_skill_level="junior",
            llm_provider="anthropic",
            llm_model_large="claude-3",
            llm_model_small="claude-instant",
            llm_temperature="0.5",
        )
        trello_ts = TaskSystem(
            board_provider="trello",
            api_key="key",
            token="token",
            board_id="board",
            base_url="https://api.trello.com/1",
        )
        config.task_systems.append(trello_ts)

        result = ConfigMapper.model_to_form_data(config)

        assert result["agent_skill_level"] == "junior"
        assert result["llm_provider"] == "anthropic"
        assert result["llm_model_large"] == "claude-3"
        assert result["llm_model_small"] == "claude-instant"
        assert result["llm_temperature"] == "0.5"

    def test_extracts_trello_fields(self, app):
        """Trello fields should be extracted from model."""
        config = AgentSettings()
        trello_ts = TaskSystem(
            board_provider="trello",
            api_key="api-key",
            token="api-token",
            board_id="board-id",
            base_url="https://api.trello.com/1",
            backlog_state="backlog",
            readfrom_state="todo",
            in_progress_state="doing",
            moveto_state="done",
        )
        config.task_systems.append(trello_ts)

        result = ConfigMapper.model_to_form_data(config)

        assert result["trello_api_key"] == "api-key"
        assert result["trello_api_token"] == "api-token"
        assert result["trello_board_id"] == "board-id"
        assert result["trello_backlog_list"] == "backlog"
        assert result["trello_readfrom_list"] == "todo"
        assert result["trello_progress_list"] == "doing"
        assert result["trello_moveto_list"] == "done"

    def test_handles_missing_task_system(self, app):
        """Missing task_systems should result in None values."""
        config = AgentSettings()

        result = ConfigMapper.model_to_form_data(config)

        assert result["trello_api_key"] is None
        assert result["trello_api_token"] is None
        assert result["trello_board_id"] is None

    def test_defaults_llm_provider_to_mistral(self, app):
        """Missing llm_provider should default to mistral."""
        config = AgentSettings(llm_provider=None)

        result = ConfigMapper.model_to_form_data(config)

        assert result["llm_provider"] == "mistral"


class TestConfigMapperFormToSchema:
    """Tests for ConfigMapper.form_to_schema."""

    def test_parses_trello_form_data(self, app):
        """Trello form data should be parsed into schema."""
        with app.test_request_context(
            "/settings",
            method="POST",
            data={
                "task_system_type": "TRELLO",
                "trello_api_key": "key",
                "trello_api_token": "token",
                "trello_board_id": "board",
                "trello_base_url": "https://api.trello.com/1",
                "trello_backlog_list": "backlog",
                "trello_readfrom_list": "todo",
                "trello_progress_list": "doing",
                "trello_moveto_list": "done",
                "llm_provider": "openai",
                "polling_interval_seconds": "90",
                "repo_type": "GITHUB",
                "github_repo_url": "https://github.com/test/repo.git",
            },
        ):
            result = ConfigMapper.form_to_schema()

            assert result.task_system_type == "TRELLO"
            assert result.trello_config is not None
            assert result.trello_config.api_key == "key"
            assert result.trello_config.api_token == "token"
            assert result.trello_config.board_id == "board"
            assert result.polling_interval_seconds == 90
            assert result.llm_config.provider == "openai"

    def test_parses_is_active_checkbox(self, app):
        """is_active checkbox should be parsed correctly."""
        with app.test_request_context(
            "/settings",
            method="POST",
            data={
                "task_system_type": "TRELLO",
                "is_active": "on",
            },
        ):
            result = ConfigMapper.form_to_schema()
            assert result.is_active is True

        with app.test_request_context(
            "/settings",
            method="POST",
            data={
                "task_system_type": "TRELLO",
            },
        ):
            result = ConfigMapper.form_to_schema()
            assert result.is_active is False


class TestConfigMapperGitHub:
    """Tests for ConfigMapper with GitHub configuration."""

    def test_applies_github_config(self, app):
        """GitHub config should be applied to model and task_system."""
        github_config = GitHubConfigSchema(
            base_url="https://api.github.com",
            api_token="ghp_test_token",
            project_owner="octocat",
            project_number=1,
            board_id="PVT_kwDOxxxxxx",
            backlog_list="Backlog",
            readfrom_list="Todo",
            progress_list="In Progress",
            moveto_list="Done",
        )
        schema = SettingsFormSchema(
            task_system_type="GITHUB",
            github_config=github_config,
        )
        settings = AgentSettings()

        result = ConfigMapper.schema_to_model(schema, settings)

        github_ts = result.get_task_system("github")
        assert github_ts is not None
        assert github_ts.backlog_state == "Backlog"
        assert github_ts.readfrom_state == "Todo"
        assert github_ts.in_progress_state == "In Progress"
        assert github_ts.moveto_state == "Done"
        assert github_ts.board_provider == "github"
        assert github_ts.token == "ghp_test_token"
        assert github_ts.project_owner == "octocat"
        assert github_ts.project_number == 1
        assert github_ts.board_id == "PVT_kwDOxxxxxx"
        assert github_ts.base_url == "https://api.github.com"

    def test_creates_github_task_system_if_missing(self, app):
        """TaskSystem should be created with github provider if not present."""
        github_config = GitHubConfigSchema(project_owner="test-org")
        schema = SettingsFormSchema(
            task_system_type="GITHUB",
            github_config=github_config,
        )
        settings = AgentSettings()
        assert len(settings.task_systems) == 0

        result = ConfigMapper.schema_to_model(schema, settings)

        github_ts = result.get_task_system("github")
        assert github_ts is not None
        assert github_ts.board_provider == "github"

    def test_extracts_github_fields(self, app):
        """GitHub fields should be extracted from model."""
        settings = AgentSettings(task_system_type="GITHUB")
        github_ts = TaskSystem(
            board_provider="github",
            token="ghp_test_token",
            project_owner="octocat",
            project_number=1,
            board_id="PVT_kwDOxxxxxx",
            base_url="https://api.github.com",
            backlog_state="Backlog",
            readfrom_state="Todo",
            in_progress_state="In Progress",
            moveto_state="Done",
        )
        settings.task_systems.append(github_ts)

        result = ConfigMapper.model_to_form_data(settings)

        assert result["github_api_token"] == "ghp_test_token"
        assert result["github_project_owner"] == "octocat"
        assert result["github_project_number"] == 1
        assert result["github_board_id"] == "PVT_kwDOxxxxxx"
        assert result["github_base_url"] == "https://api.github.com"
        assert result["github_backlog_list"] == "Backlog"
        assert result["github_readfrom_list"] == "Todo"
        assert result["github_progress_list"] == "In Progress"
        assert result["github_moveto_list"] == "Done"

    def test_parses_github_form_data(self, app):
        """GitHub form data should be parsed into schema."""
        with app.test_request_context(
            "/settings",
            method="POST",
            data={
                "task_system_type": "GITHUB",
                "github_api_token": "ghp_test_token",
                "github_project_owner": "octocat",
                "github_project_number": "1",
                "github_board_id": "PVT_kwDOxxxxxx",
                "github_base_url": "https://api.github.com",
                "github_backlog_list": "Backlog",
                "github_readfrom_list": "Todo",
                "github_progress_list": "In Progress",
                "github_moveto_list": "Done",
                "llm_provider": "openai",
                "polling_interval_seconds": "90",
                "repo_type": "GITHUB",
            },
        ):
            result = ConfigMapper.form_to_schema()

            assert result.task_system_type == "GITHUB"
            assert result.github_config is not None
            assert result.github_config.api_token == "ghp_test_token"
            assert result.github_config.project_owner == "octocat"
            assert result.github_config.project_number == 1
            assert result.github_config.board_id == "PVT_kwDOxxxxxx"
            assert result.github_config.backlog_list == "Backlog"
            # trello_config is now always parsed (not None)
            assert result.trello_config is not None

    def test_handles_missing_github_task_system(self, app):
        """Missing GitHub task_system should result in default values."""
        settings = AgentSettings(task_system_type="TRELLO")

        result = ConfigMapper.model_to_form_data(settings)

        assert result["github_api_token"] is None
        assert result["github_project_owner"] is None
        assert result["github_project_number"] is None
        assert result["github_board_id"] is None
        assert result["github_base_url"] == "https://api.github.com"

    def test_github_token_prefills_from_env(self, app, monkeypatch):
        """GitHub token should fall back to GITHUB_TOKEN env when not stored."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        settings = AgentSettings(task_system_type="TRELLO")

        result = ConfigMapper.model_to_form_data(settings)

        assert result["github_api_token"] == "env_token"
