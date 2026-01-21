"""Service layer for settings management.

This module contains business logic for managing agent configuration settings,
separating concerns from the route handlers and database operations.
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple

from app.agent.integrations.github_client import get_project_id_sync
from app.core.constants import LLM_PROVIDER_API_ENV
from app.core.extensions import db
from app.core.models import AgentConfig
from app.web.mappers.config_mapper import ConfigMapper
from app.web.schemas.settings_schema import SettingsFormSchema

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing agent configuration settings."""

    @staticmethod
    def get_or_create_config() -> AgentConfig:
        """Retrieve existing config or create a new one with defaults.

        Returns:
            AgentConfig instance (may be transient if newly created).
        """
        config = AgentConfig.query.first()
        if not config:
            config = AgentConfig(task_system_type="TRELLO")
        return config

    @staticmethod
    def save_settings(schema: SettingsFormSchema, config: AgentConfig) -> AgentConfig:
        """Save settings from validated schema to database.

        Args:
            schema: Validated settings form schema.
            config: AgentConfig to update.

        Returns:
            Updated and persisted AgentConfig.

        Raises:
            ValueError: If GitHub project ID cannot be fetched.
        """
        ConfigMapper.schema_to_model(schema, config)

        if schema.task_system_type == "GITHUB" and schema.github_config:
            SettingsService._fetch_github_project_id(schema, config)

        if not config.id:
            db.session.add(config)

        db.session.commit()
        logger.info("Settings saved for config id=%s", config.id)
        return config

    @staticmethod
    def _fetch_github_project_id(
        schema: SettingsFormSchema, config: AgentConfig
    ) -> None:
        """Fetch and store GitHub project ID if owner and number are provided.

        Args:
            schema: The validated settings form schema.
            config: The AgentConfig to update.

        Raises:
            ValueError: If project cannot be found or API call fails.
        """
        github_config = schema.github_config
        if not github_config:
            return

        project_owner = github_config.project_owner
        project_number = github_config.project_number

        if not project_owner or project_number is None:
            logger.info("GitHub project owner or number not provided, skipping ID fetch")
            return

        if github_config.board_id:
            logger.info("GitHub project ID already set: %s", github_config.board_id)
            return

        base_url = github_config.base_url or "https://api.github.com"

        logger.info(
            "Fetching GitHub project ID for owner=%s, number=%s",
            project_owner,
            project_number,
        )

        try:
            api_token = github_config.api_token
            project_id = get_project_id_sync(
                project_owner, project_number, base_url, api_token
            )
            github_task_system = config.get_task_system("github")
            if github_task_system:
                github_task_system.board_id = project_id
                logger.info("GitHub project ID fetched and stored: %s", project_id)
        except RuntimeError as e:
            logger.error("Failed to fetch GitHub project ID: %s", e)
            raise ValueError(
                f"Failed to fetch GitHub project ID: {e}. "
                f"Please verify the project owner and number are correct."
            ) from e

    @staticmethod
    def get_form_data(config: AgentConfig) -> Dict[str, Any]:
        """Get form data dictionary for template rendering.

        Args:
            config: AgentConfig to convert.

        Returns:
            Dictionary suitable for populating the settings form.
        """
        return ConfigMapper.model_to_form_data(config)

    @staticmethod
    def get_template_context(config: AgentConfig) -> Dict[str, Any]:
        """Build complete template context for settings page.

        Args:
            config: AgentConfig model.

        Returns:
            Dictionary with all template variables.
        """
        form_data = SettingsService.get_form_data(config)
        selected_provider = form_data.get("llm_provider", "mistral")

        missing_env = SettingsService._check_missing_provider_env(selected_provider)
        show_ollama_warning = (
            selected_provider == "ollama"
            and not os.environ.get("OLLAMA_API_KEY")
        )

        if not config.github_repo_url:
            config.github_repo_url = os.environ.get("GITHUB_REPO_URL", "")

        return {
            "config": config,
            "form_data": form_data,
            "selected_provider": selected_provider,
            "missing_provider_env": missing_env,
            "show_ollama_warning": show_ollama_warning,
        }

    @staticmethod
    def _check_missing_provider_env(provider: str) -> Optional[str]:
        """Check if required environment variable is missing for provider.

        Args:
            provider: LLM provider name.

        Returns:
            Name of missing env var, or None if present/not required.
        """
        if provider == "ollama":
            return None

        env_name = LLM_PROVIDER_API_ENV.get(provider)
        if not env_name:
            return None

        if os.environ.get(env_name):
            return None

        return env_name

    @staticmethod
    def validate_and_save(config: AgentConfig) -> Tuple[bool, Optional[str]]:
        """Validate form data and save settings.

        Args:
            config: AgentConfig to update.

        Returns:
            Tuple of (success, error_message).
        """
        try:
            schema = ConfigMapper.form_to_schema()
            SettingsService.save_settings(schema, config)
            return True, None
        except ValueError as e:
            logger.warning("Validation error saving settings: %s", e)
            return False, str(e)
