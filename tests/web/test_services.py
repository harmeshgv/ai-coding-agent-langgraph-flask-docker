"""Tests for web layer services."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from app.core.extensions import db
from app.core.models import AgentConfig, TaskSystem
from app.web.schemas.settings_schema import (
    LLMConfigSchema,
    SettingsFormSchema,
)
from app.web.services.dashboard_service import DashboardService
from app.web.services.settings_service import SettingsService


class TestDashboardService:
    """Tests for DashboardService."""

    def test_get_plan_content_returns_file_content(self):
        """Should return content of plan.md when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = os.path.join(tmpdir, "plan.md")
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write("# Test Plan\n\nThis is a test.")

            with patch.dict(os.environ, {"WORKSPACE": tmpdir}):
                result = DashboardService.get_plan_content()

            assert "# Test Plan" in result
            assert "This is a test." in result

    def test_get_plan_content_returns_default_when_missing(self):
        """Should return default message when plan.md doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"WORKSPACE": tmpdir}):
                result = DashboardService.get_plan_content()

            assert "No plan.md found" in result

    def test_get_template_context_includes_plan_content(self):
        """Template context should include plan_content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = os.path.join(tmpdir, "plan.md")
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write("# My Plan")

            with patch.dict(os.environ, {"WORKSPACE": tmpdir}):
                result = DashboardService.get_template_context()

            assert "plan_content" in result
            assert "# My Plan" in result["plan_content"]


class TestSettingsService:
    """Tests for SettingsService."""

    def test_get_or_create_config_returns_existing(self, app):
        """Should return existing config if one exists."""
        with app.app_context():
            existing = AgentConfig(task_system_type="TRELLO")
            trello_ts = TaskSystem(
                task_system_type="TRELLO",
                board_provider="trello",
            )
            existing.task_systems.append(trello_ts)
            db.session.add(existing)
            db.session.commit()
            existing_id = existing.id

            result = SettingsService.get_or_create_config()

            assert result.id == existing_id

    def test_get_or_create_config_creates_new(self, app):
        """Should create new config with defaults if none exists."""
        with app.app_context():
            result = SettingsService.get_or_create_config()

            assert result is not None
            assert result.task_system_type == "TRELLO"

    def test_save_settings_persists_to_db(self, app):
        """Should persist settings to database."""
        with app.app_context():
            config = AgentConfig(task_system_type="TRELLO")
            schema = SettingsFormSchema(
                task_system_type="TRELLO",
                agent_skill_level="senior",
                polling_interval_seconds=120,
                is_active=True,
                llm_config=LLMConfigSchema(provider="openai"),
            )

            result = SettingsService.save_settings(schema, config)

            assert result.id is not None
            assert result.agent_skill_level == "senior"
            assert result.polling_interval_seconds == 120
            assert result.is_active is True

            reloaded = db.session.get(AgentConfig, result.id)
            assert reloaded.agent_skill_level == "senior"

    def test_save_settings_updates_existing(self, app):
        """Should update existing config."""
        with app.app_context():
            existing = AgentConfig(
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

            result = SettingsService.save_settings(schema, existing)

            assert result.id == existing_id
            assert result.agent_skill_level == "senior"

    def test_get_template_context_includes_required_keys(self, app):
        """Template context should include all required keys."""
        with app.app_context():
            config = AgentConfig(
                task_system_type="TRELLO",
                llm_provider="mistral",
            )

            result = SettingsService.get_template_context(config)

            assert "config" in result
            assert "form_data" in result
            assert "selected_provider" in result
            assert "missing_provider_env" in result
            assert "show_ollama_warning" in result

    def test_check_missing_provider_env_returns_none_for_ollama(self, app):
        """Ollama should not require env var."""
        result = SettingsService._check_missing_provider_env("ollama")
        assert result is None

    def test_check_missing_provider_env_returns_env_name_when_missing(self, app):
        """Should return env var name when missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = SettingsService._check_missing_provider_env("openai")
            assert result == "OPENAI_API_KEY"

    def test_check_missing_provider_env_returns_none_when_present(self, app):
        """Should return None when env var is present."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            result = SettingsService._check_missing_provider_env("openai")
            assert result is None

    def test_validate_and_save_success(self, app):
        """Should return success tuple on valid save."""
        with app.app_context():
            config = AgentConfig(task_system_type="TRELLO")

            with app.test_request_context(
                "/settings",
                method="POST",
                data={
                    "task_system_type": "TRELLO",
                    "polling_interval_seconds": "60",
                    "llm_provider": "mistral",
                },
            ):
                success, error_msg = SettingsService.validate_and_save(config)

            assert success is True
            assert error_msg is None
