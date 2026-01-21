"""Mappers for converting between web schemas and database models.

This module provides bidirectional mapping between:
- Web layer schemas (Pydantic models for form data)
- Database layer models (SQLAlchemy ORM models)
"""

import os
from typing import Any, Dict

from flask import request

from app.core.models import AgentSettings, TaskSystem
from app.web.schemas.settings_schema import (
    GitHubConfigSchema,
    JiraConfigSchema,
    LLMConfigSchema,
    SettingsFormSchema,
    TrelloConfigSchema,
)


class ConfigMapper:
    """Maps between web schemas and database models for configuration."""

    @staticmethod
    def form_to_schema() -> SettingsFormSchema:
        """Parse Flask form data into a validated SettingsFormSchema.

        Returns:
            SettingsFormSchema with validated form data.
        """
        task_system_type = request.form.get("task_system_type", "TRELLO")

        # Always parse all provider configs from form
        trello_config = TrelloConfigSchema(
            api_key=request.form.get("trello_api_key"),
            api_token=request.form.get("trello_api_token"),
            base_url=request.form.get(
                "trello_base_url", "https://api.trello.com/1"
            ),
            board_id=request.form.get("trello_board_id"),
            backlog_list=request.form.get("trello_backlog_list"),
            readfrom_list=request.form.get("trello_readfrom_list"),
            progress_list=request.form.get("trello_progress_list"),
            moveto_list=request.form.get("trello_moveto_list"),
        )
        github_config = GitHubConfigSchema(
            base_url=request.form.get(
                "github_base_url", "https://api.github.com"
            ),
            api_token=request.form.get("github_api_token"),
            project_owner=request.form.get("github_project_owner"),
            project_number=request.form.get("github_project_number"),
            board_id=request.form.get("github_board_id"),
            backlog_list=request.form.get("github_backlog_list"),
            readfrom_list=request.form.get("github_readfrom_list"),
            progress_list=request.form.get("github_progress_list"),
            moveto_list=request.form.get("github_moveto_list"),
        )
        jira_config = JiraConfigSchema(
            username=request.form.get("jira_username"),
            api_token=request.form.get("jira_api_token"),
            jql_query=request.form.get("jira_jql_query"),
        )

        llm_config = LLMConfigSchema(
            provider=request.form.get("llm_provider"),
            model_large=request.form.get("llm_model_large"),
            model_small=request.form.get("llm_model_small"),
            temperature=request.form.get("llm_temperature"),
        )

        return SettingsFormSchema(
            task_system_type=task_system_type,
            agent_skill_level=request.form.get("agent_skill_level"),
            polling_interval_seconds=request.form.get("polling_interval_seconds"),
            repo_type=request.form.get("repo_type", "GITHUB"),
            github_repo_url=request.form.get("github_repo_url"),
            is_active="is_active" in request.form,
            trello_config=trello_config,
            github_config=github_config,
            jira_config=jira_config,
            llm_config=llm_config,
        )

    @staticmethod
    def schema_to_model(
        schema: SettingsFormSchema, settings: AgentSettings
    ) -> AgentSettings:
        """Apply schema values to an AgentSettings model.

        Args:
            schema: Validated settings form schema.
            settings: Existing AgentSettings to update (or new instance).

        Returns:
            Updated AgentSettings model (not yet committed).
        """
        settings.task_system_type = schema.task_system_type
        settings.agent_skill_level = schema.agent_skill_level
        settings.polling_interval_seconds = schema.polling_interval_seconds
        settings.repo_type = schema.repo_type
        settings.github_repo_url = schema.github_repo_url
        settings.is_active = schema.is_active

        ConfigMapper._apply_llm_config(schema.llm_config, settings)

        # Always save all provider configs
        if schema.trello_config:
            ConfigMapper._apply_trello_config(schema.trello_config, settings)
        if schema.github_config:
            ConfigMapper._apply_github_config(schema.github_config, settings)

        return settings

    @staticmethod
    def _apply_llm_config(llm_schema: LLMConfigSchema, settings: AgentSettings) -> None:
        """Apply LLM configuration from schema to model."""
        settings.llm_provider = llm_schema.provider
        settings.llm_model_large = llm_schema.model_large
        settings.llm_model_small = llm_schema.model_small
        settings.llm_temperature = llm_schema.temperature

    @staticmethod
    def _apply_trello_config(
        trello_schema: TrelloConfigSchema, settings: AgentSettings
    ) -> None:
        """Apply Trello configuration from schema to model."""
        task_system = ConfigMapper._get_or_create_task_system(settings, "trello")
        task_system.board_provider = "trello"
        task_system.task_system_type = "TRELLO"

        task_system.board_id = trello_schema.board_id
        task_system.api_key = trello_schema.api_key
        task_system.token = trello_schema.api_token
        task_system.base_url = trello_schema.base_url
        task_system.backlog_state = trello_schema.backlog_list
        task_system.readfrom_state = trello_schema.readfrom_list
        task_system.in_progress_state = trello_schema.progress_list
        task_system.moveto_state = trello_schema.moveto_list

    @staticmethod
    def _apply_github_config(
        github_schema: GitHubConfigSchema, settings: AgentSettings
    ) -> None:
        """Apply GitHub Projects configuration from schema to model."""
        task_system = ConfigMapper._get_or_create_task_system(settings, "github")
        task_system.board_provider = "github"
        task_system.task_system_type = "GITHUB"

        task_system.token = github_schema.api_token
        task_system.project_owner = github_schema.project_owner
        task_system.project_number = github_schema.project_number
        task_system.board_id = github_schema.board_id
        task_system.base_url = github_schema.base_url
        task_system.backlog_state = github_schema.backlog_list
        task_system.readfrom_state = github_schema.readfrom_list
        task_system.in_progress_state = github_schema.progress_list
        task_system.moveto_state = github_schema.moveto_list

    @staticmethod
    def _get_or_create_task_system(
        settings: AgentSettings, provider: str
    ) -> TaskSystem:
        """Get existing TaskSystem for provider or create a new one."""
        existing = settings.get_task_system(provider)
        if existing:
            return existing

        task_system = TaskSystem(
            task_system_type=provider.upper(),
            board_provider=provider,
        )
        settings.task_systems.append(task_system)
        return task_system

    @staticmethod
    def model_to_form_data(settings: AgentSettings) -> Dict[str, Any]:
        """Convert AgentSettings model to form data dictionary for template rendering.

        Args:
            settings: AgentSettings model to convert.

        Returns:
            Dictionary suitable for populating the settings form template.
        """
        form_data: Dict[str, Any] = {
            "agent_skill_level": settings.agent_skill_level,
            "llm_provider": settings.llm_provider or "mistral",
            "llm_model_large": settings.llm_model_large,
            "llm_model_small": settings.llm_model_small,
            "llm_temperature": settings.llm_temperature,
        }

        ConfigMapper._add_trello_form_data(settings, form_data)
        ConfigMapper._add_github_form_data(settings, form_data)
        ConfigMapper._add_jira_form_data(form_data)

        return form_data

    @staticmethod
    def _add_trello_form_data(settings: AgentSettings, form_data: Dict[str, Any]) -> None:
        """Add Trello-specific fields to form data."""
        task_system = settings.get_task_system("trello")
        if task_system:
            form_data["trello_api_key"] = task_system.api_key
            form_data["trello_api_token"] = task_system.token
            form_data["trello_board_id"] = task_system.board_id
            form_data["trello_base_url"] = task_system.base_url
            form_data["trello_backlog_list"] = task_system.backlog_state
            form_data["trello_readfrom_list"] = task_system.readfrom_state
            form_data["trello_progress_list"] = task_system.in_progress_state
            form_data["trello_moveto_list"] = task_system.moveto_state
        else:
            form_data["trello_api_key"] = None
            form_data["trello_api_token"] = None
            form_data["trello_board_id"] = None
            form_data["trello_base_url"] = None
            form_data["trello_backlog_list"] = None
            form_data["trello_readfrom_list"] = None
            form_data["trello_progress_list"] = None
            form_data["trello_moveto_list"] = None

    @staticmethod
    def _add_github_form_data(settings: AgentSettings, form_data: Dict[str, Any]) -> None:
        """Add GitHub Projects-specific fields to form data."""
        task_system = settings.get_task_system("github")
        env_token = os.environ.get("GITHUB_TOKEN")
        if task_system:
            form_data["github_api_token"] = task_system.token or env_token
            form_data["github_project_owner"] = task_system.project_owner
            form_data["github_project_number"] = task_system.project_number
            form_data["github_board_id"] = task_system.board_id
            form_data["github_base_url"] = task_system.base_url or "https://api.github.com"
            form_data["github_backlog_list"] = task_system.backlog_state
            form_data["github_readfrom_list"] = task_system.readfrom_state
            form_data["github_progress_list"] = task_system.in_progress_state
            form_data["github_moveto_list"] = task_system.moveto_state
        else:
            form_data["github_api_token"] = env_token
            form_data["github_project_owner"] = None
            form_data["github_project_number"] = None
            form_data["github_board_id"] = None
            form_data["github_base_url"] = "https://api.github.com"
            form_data["github_backlog_list"] = None
            form_data["github_readfrom_list"] = None
            form_data["github_progress_list"] = None
            form_data["github_moveto_list"] = None

    @staticmethod
    def _add_jira_form_data(form_data: Dict[str, Any]) -> None:
        """Add Jira-specific fields to form data (placeholder)."""
        form_data["jira_username"] = "JIRA_USERNAME"
        form_data["jira_api_token"] = "JIRA_API_TOKEN"
        form_data["jira_jql_query"] = "JIRA_JQL_QUERY"
