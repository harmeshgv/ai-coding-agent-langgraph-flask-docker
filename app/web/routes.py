"""The routes for the web application.

This module uses a Flask Blueprint to organize the routes. It includes
the main route for the application, which displays and handles the
configuration form for the AI agent. This includes logic for saving
and retrieving settings for task management systems, repositories,
and LLM providers, as well as handling encryption of sensitive data.
"""

import json
import logging
import os
from typing import Any

from core.constants import LLM_PROVIDER_API_ENV
from core.extensions import db, scheduler
from core.models import AgentConfig
from cryptography.fernet import Fernet, InvalidToken
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

logger = logging.getLogger(__name__)

# 1. Blueprint erstellen
# 'web' = Name des Blueprints (für url_for('web.index'))
# __name__ = Damit Flask weiß, wo Templates/Static files für diesen Blueprint liegen
web_bp = Blueprint("web", __name__, template_folder="templates")


def _missing_provider_env(provider: str) -> str | None:
    if provider == "ollama":
        return None
    env_name = LLM_PROVIDER_API_ENV.get(provider)
    if not env_name:
        return None
    if os.environ.get(env_name):
        return None
    return env_name


def _get_trello_data() -> dict[str, Any]:
    """Get Trello data from form"""
    return {
        "env": {
            "TRELLO_API_KEY": request.form.get("trello_api_key"),
            "TRELLO_TOKEN": request.form.get("trello_api_token"),
            "TRELLO_BASE_URL": request.form.get(
                "trello_base_url", "https://api.trello.com/1"
            ),
        },
        "trello_board_id": request.form.get("trello_board_id"),
        "trello_readfrom_list": request.form.get("trello_readfrom_list"),
        "trello_progress_list": request.form.get("trello_progress_list"),
        "trello_moveto_list": request.form.get("trello_moveto_list"),
    }


def _get_jira_data() -> dict[str, Any]:
    """Get Jira data from form"""
    return {
        "env": {
            "JIRA_URL": os.environ.get("JIRA_URL"),  # Assuming this is set elsewhere
            "JIRA_USERNAME": request.form.get("jira_username"),
            "JIRA_API_TOKEN": request.form.get("jira_api_token"),
        },
        "jql": request.form.get("jira_jql_query"),
    }


def _get_llm_config() -> dict[str, Any]:
    """Get LLM config from form"""
    return {
        "llm_provider": request.form.get("llm_provider"),
        "llm_model_large": request.form.get("llm_model_large"),
        "llm_model_small": request.form.get("llm_model_small"),
        "llm_temperature": request.form.get("llm_temperature"),
    }


def index_post(config: AgentConfig, encryption_key: Fernet):
    """Update agent configuration from form"""
    # Update generic fields
    config.task_system_type = request.form.get("task_system_type")
    config.repo_type = request.form.get("repo_type")
    config.github_repo_url = request.form.get("github_repo_url")
    config.is_active = "is_active" in request.form
    config.agent_skill_level = request.form.get("agent_skill_level")
    try:
        polling_interval = int(request.form.get("polling_interval_seconds", 60))
        config.polling_interval_seconds = polling_interval
    except (ValueError, TypeError):
        flash("Invalid polling interval. Please enter a number.", "danger")
        polling_interval = 60  # Fallback

    # Create JSON from the specific fields for the selected system

    # Decrypt and load existing data first, to not lose settings from other cards
    try:
        decrypted_json = encryption_key.decrypt(
            config.system_config_json.encode()
        ).decode()
        new_config_data = json.loads(decrypted_json or "{}")
    except (InvalidToken, TypeError, AttributeError, json.JSONDecodeError):
        new_config_data = {}  # Start fresh if decryption fails or data is invalid

    system_type = config.task_system_type

    if system_type == "TRELLO":
        new_config_data.update(_get_trello_data())
    elif system_type == "JIRA":
        new_config_data.update(_get_jira_data())

    new_config_data.update(_get_llm_config())

    # Encrypt the JSON configuration
    json_config_str = json.dumps(new_config_data, indent=2)
    encrypted_config = encryption_key.encrypt(json_config_str.encode()).decode()
    config.system_config_json = encrypted_config

    if not config.id:
        db.session.add(config)
    db.session.commit()

    # Reschedule job
    if scheduler.get_job("agent_job"):
        scheduler.scheduler.reschedule_job(
            "agent_job", trigger="interval", seconds=polling_interval
        )

    flash("Configuration saved successfully!", "success")
    return redirect(url_for("web.index"))


def _set_trello_form_data(saved_data: dict[str, Any], form_data: dict):
    """Set Trello form data."""
    form_data["trello_api_key"] = saved_data.get("env", {}).get("TRELLO_API_KEY")
    form_data["trello_api_token"] = saved_data.get("env", {}).get("TRELLO_TOKEN")
    form_data["trello_board_id"] = saved_data.get("trello_board_id")
    form_data["trello_readfrom_list"] = saved_data.get("trello_readfrom_list")
    form_data["trello_progress_list"] = saved_data.get("trello_progress_list")
    form_data["trello_moveto_list"] = saved_data.get("trello_moveto_list")
    form_data["trello_base_url"] = saved_data.get("env", {}).get(
        "TRELLO_BASE_URL", "https://api.trello.com/1"
    )


def _set_jira_form_data(saved_data: dict[str, Any], form_data: dict):
    """Set Jira form data."""
    form_data["jira_username"] = saved_data.get("env", {}).get("JIRA_USERNAME")
    form_data["jira_api_token"] = saved_data.get("env", {}).get("JIRA_API_TOKEN")
    form_data["jira_jql_query"] = saved_data.get("jql")


def _set_llm_form_data(saved_data: dict[str, Any], form_data: dict):
    """Set LLM form data."""
    form_data["llm_provider"] = saved_data.get("llm_provider", "mistral")
    form_data["llm_model_large"] = saved_data.get("llm_model_large")
    form_data["llm_model_small"] = saved_data.get("llm_model_small")
    form_data["llm_temperature"] = saved_data.get("llm_temperature", 0.0)


def index_get(config: AgentConfig, encryption_key: Fernet) -> str:
    """
    Get agent configuration from form.
    Decrypt and parse JSON to populate form
    """
    form_data = {}
    form_data["agent_skill_level"] = config.agent_skill_level

    if config.system_config_json:
        try:
            decrypted_json = encryption_key.decrypt(
                config.system_config_json.encode()
            ).decode()
            saved_data = json.loads(decrypted_json or "{}")

            # Populate form_data with prefixed keys for the template
            # Trello data
            _set_trello_form_data(saved_data, form_data)

            # Jira data
            _set_jira_form_data(saved_data, form_data)

            # LLM data
            _set_llm_form_data(saved_data, form_data)

        except (InvalidToken, TypeError, AttributeError, json.JSONDecodeError):
            flash(
                "Could not parse or decrypt existing configuration. It may be legacy data. "
                + "Re-saving will fix it.",
                "warning",
            )
    if not form_data.get("llm_provider"):
        form_data["llm_provider"] = "mistral"

    selected_provider = form_data.get("llm_provider", "mistral")
    missing_provider_env = _missing_provider_env(selected_provider)
    show_ollama_warning = selected_provider == "ollama" and not os.environ.get(
        "OLLAMA_API_KEY"
    )

    return render_template(
        "index.html",
        config=config,
        form_data=form_data,
        selected_provider=selected_provider,
        missing_provider_env=missing_provider_env,
        show_ollama_warning=show_ollama_warning,
    )


# 2. Routen definieren (ACHTUNG: @web_bp statt @app)
@web_bp.route("/", methods=["GET", "POST"])
def index():
    """Handles the main configuration page."""
    encryption_key = current_app.config["FERNET_KEY"]
    config = AgentConfig.query.first()
    if not config:
        config = AgentConfig(task_system_type="TRELLO", system_config_json="{}")

    if request.method == "POST":
        return index_post(config, encryption_key)

    return index_get(config, encryption_key)
