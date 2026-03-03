"""Tests for web layer services."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.core.extensions import db
from app.core.localdb.models import AgentSettings, TaskSystem
from app.web.schemas.settings_schema import (
    LLMConfigSchema,
    SettingsFormSchema,
)
from app.web.services import settings_service


class TestSettingsService:
    """Tests for SettingsService."""

    def test_get_or_create_settings_returns_existing(self, app):
        """Should return existing config if one exists."""
        with app.app_context():
            existing = AgentSettings(task_system_type="TRELLO")
            trello_ts = TaskSystem(
                task_system_type="TRELLO",
                task_provider="trello",
            )
            existing.task_systems.append(trello_ts)
            db.session.add(existing)
            db.session.commit()
            existing_id = existing.id

            result = settings_service.get_or_create_settings()

            assert result.id == existing_id

    def test_get_or_create_settings_creates_new(self, app):
        """Should create new config with defaults if none exists."""
        with app.app_context():
            result = settings_service.get_or_create_settings()

            assert result is not None
            assert result.task_system_type == "TRELLO"

    def test_save_settings_persists_to_db(self, app):
        """Should persist settings to database."""
        with app.app_context():
            settings = AgentSettings(task_system_type="TRELLO")
            schema = SettingsFormSchema(
                task_system_type="TRELLO",
                agent_skill_level="senior",
                polling_interval_seconds=120,
                is_active=True,
                llm_config=LLMConfigSchema(provider="openai"),
            )

            result = settings_service.save_settings(schema, settings)

            assert result.id is not None
            assert result.agent_skill_level == "senior"
            assert result.polling_interval_seconds == 120
            assert result.is_active is True

            reloaded = db.session.get(AgentSettings, result.id)
            assert reloaded.agent_skill_level == "senior"

    def test_save_settings_updates_existing(self, app):
        """Should update existing config."""
        with app.app_context():
            existing = AgentSettings(
                task_system_type="TRELLO",
                agent_skill_level="junior",
            )
            db.session.add(existing)
            db.session.commit()
            existing_id = existing.id

            schema = SettingsFormSchema(
                task_system_type="TRELLO",
                agent_skill_level="senior",
                llm_config=LLMConfigSchema(provider="mistral"),
            )

            result = settings_service.save_settings(schema, existing)

            assert result.id == existing_id
            assert result.agent_skill_level == "senior"

    def test_get_template_context_includes_required_keys(self, app):
        """Template context should include all required keys."""
        with app.app_context():
            settings = AgentSettings(
                task_system_type="TRELLO",
                llm_provider="mistral",
            )

            result = settings_service.get_template_context(settings)

            assert "settings" in result
            assert "form_data" in result
            assert "selected_provider" in result
            assert "missing_provider_env" in result
            assert "show_ollama_warning" in result

    def test_check_missing_provider_env_returns_none_for_ollama(self, app):
        """Ollama should not require env var."""
        result = settings_service._check_missing_provider_env("ollama")
        assert result is None

    def test_check_missing_provider_env_returns_env_name_when_missing(self, app):
        """Should return env var name when missing."""
        from app.core.config import set_env_settings

        # Clear only OPENAI_API_KEY, keep required vars
        env_without_openai = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env_without_openai, clear=True):
            set_env_settings(None)  # Reset to reload from new environment
            result = settings_service._check_missing_provider_env("openai")
            assert result == "OPENAI_API_KEY"

    def test_check_missing_provider_env_returns_none_when_present(self, app):
        """Should return None when env var is present."""
        from app.core.config import set_env_settings

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            set_env_settings(None)  # Reset to reload from new environment
            result = settings_service._check_missing_provider_env("openai")
            assert result is None

    def test_validate_and_save_success(self, app):
        """Should return success tuple on valid save."""
        with app.app_context():
            settings = AgentSettings(task_system_type="TRELLO")

            with app.test_request_context(
                "/settings",
                method="POST",
                data={
                    "task_system_type": "TRELLO",
                    "polling_interval_seconds": "60",
                    "llm_provider": "mistral",
                },
            ):
                success, error_msg = settings_service.validate_and_save(settings)

            assert success is True
            assert error_msg is None
