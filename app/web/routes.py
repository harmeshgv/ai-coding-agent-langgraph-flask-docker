"""The routes for the web application.

This module uses a Flask Blueprint to organize the routes. It includes
the main route for the application, which displays and handles the
configuration form for the AI agent. This includes logic for saving
and retrieving settings for task management systems, repositories,
and LLM providers, as well as handling encryption of sensitive data.
"""

import logging
import os
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.core.constants import LLM_PROVIDER_API_ENV
from app.core.extensions import db
from app.core.models import AgentConfig, TaskSystem

logger = logging.getLogger(__name__)

# 1. Blueprint erstellen
# 'web' = Name des Blueprints (für url_for('web.index'))
# __name__ = Damit Flask weiß, wo Templates/Static files für diesen Blueprint liegen
web_bp = Blueprint(
    "web", __name__, template_folder="templates", static_folder="../static"
)


def _missing_provider_env(provider: str) -> str | None:
    if provider == "ollama":
        return None
    env_name = LLM_PROVIDER_API_ENV.get(provider)
    if not env_name:
        return None
    if os.environ.get(env_name):
        return None
    return env_name


def _normalize_form_value(value: Any) -> Any:
    """Convert empty strings to None for easier persistence."""
    return value if value not in ("", None) else None


def _get_trello_data() -> dict[str, Any]:
    """Get Trello data from form"""
    return {
        "board_provider": "trello",
        "env": {
            "TRELLO_API_KEY": request.form.get("trello_api_key"),
            "TRELLO_TOKEN": request.form.get("trello_api_token"),
            "TRELLO_BASE_URL": request.form.get(
                "trello_base_url", "https://api.trello.com/1"
            ),
        },
        "trello_board_id": request.form.get("trello_board_id"),
        "task_backlog_state": request.form.get("trello_backlog_list"),
        "task_readfrom_state": request.form.get("trello_readfrom_list"),
        "task_in_progress_state": request.form.get("trello_progress_list"),
        "task_moveto_state": request.form.get("trello_moveto_list"),
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


def _get_or_create_task_system(config: AgentConfig) -> TaskSystem:
    task_system = config.task_system
    if not task_system:
        task_system = TaskSystem(
            task_system_type=config.task_system_type,
            board_provider="trello",
        )
        config.task_system = task_system
    return task_system


def _update_trello_config(config: AgentConfig, new_config_data: dict):
    """Update Trello configuration from form data."""
    trello_data = _get_trello_data()

    config.task_backlog_state = _normalize_form_value(
        trello_data.pop("task_backlog_state", None)
    )
    config.task_readfrom_state = _normalize_form_value(
        trello_data.pop("task_readfrom_state", None)
    )
    config.task_in_progress_state = _normalize_form_value(
        trello_data.pop("task_in_progress_state", None)
    )
    config.task_moveto_state = _normalize_form_value(
        trello_data.pop("task_moveto_state", None)
    )

    task_system = _get_or_create_task_system(config)
    board_provider = trello_data.pop("board_provider", None)
    if board_provider:
        task_system.board_provider = board_provider
    board_id = trello_data.pop("trello_board_id", None)
    if board_id:
        task_system.board_id = board_id

    env_config = trello_data.pop("env", {}) or {}
    api_key = env_config.get("TRELLO_API_KEY")
    token = env_config.get("TRELLO_TOKEN")
    base_url = env_config.get("TRELLO_BASE_URL")
    if api_key:
        task_system.api_key = api_key
    if token:
        task_system.token = token
    if base_url:
        task_system.base_url = base_url

    new_config_data.update(trello_data)


def _update_llm_config(config: AgentConfig):
    """Update LLM configuration from form data."""
    llm_config = _get_llm_config()
    config.llm_provider = _normalize_form_value(llm_config.get("llm_provider")) or "mistral"
    config.llm_model_large = _normalize_form_value(llm_config.get("llm_model_large"))
    config.llm_model_small = _normalize_form_value(llm_config.get("llm_model_small"))
    config.llm_temperature = _normalize_form_value(llm_config.get("llm_temperature"))


def settings_post(config: AgentConfig):
    """Update agent settings from form"""
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

    # Load existing data first, to not lose settings from other cards
    existing_config = config.system_config or {}
    if not isinstance(existing_config, dict):
        existing_config = {}
    new_config_data = dict(existing_config)

    system_type = config.task_system_type

    if system_type == "TRELLO":
        _update_trello_config(config, new_config_data)
    elif system_type == "JIRA":
        new_config_data.update(_get_jira_data())

    _update_llm_config(config)


    # Assign dict directly; EncryptedString handles serialization/encryption
    config.system_config = new_config_data

    if not config.id:
        db.session.add(config)
    db.session.commit()

    flash("Settings saved successfully!", "success")
    return redirect(url_for("web.settings"))


def _set_trello_form_data(config: AgentConfig, form_data: dict):
    """Set Trello form data."""
    task_system = config.task_system

    form_data["trello_api_key"] = task_system.api_key
    form_data["trello_api_token"] = task_system.token
    form_data["trello_board_id"] = task_system.board_id
    form_data["trello_backlog_list"] = config.task_backlog_state
    form_data["trello_readfrom_list"] = config.task_readfrom_state
    form_data["trello_progress_list"] = config.task_in_progress_state
    form_data["trello_moveto_list"] = config.task_moveto_state
    form_data["trello_base_url"] = task_system.base_url


def _set_jira_form_data(config: AgentConfig, form_data: dict):
    """Set Jira form data."""
    form_data["jira_username"] = "JIRA_USERNAME"
    form_data["jira_api_token"] = "JIRA_API_TOKEN"
    form_data["jira_jql_query"] = "JIRA_JQL_QUERY"


def _set_llm_form_data(config: AgentConfig, form_data: dict):
    """Set LLM form data."""
    form_data["llm_provider"] = config.llm_provider or "mistral"
    form_data["llm_model_large"] = config.llm_model_large
    form_data["llm_model_small"] = config.llm_model_small
    form_data["llm_temperature"] = config.llm_temperature


def settings_get(config: AgentConfig) -> str:
    """
    Get agent settings from form.
    Decrypt and parse JSON to populate form
    """
    form_data = {}
    form_data["agent_skill_level"] = config.agent_skill_level

    # Populate form_data with prefixed keys for the template
    # Trello data
    _set_trello_form_data(config, form_data)

    # Jira data
    _set_jira_form_data(config, form_data)

    # LLM data
    _set_llm_form_data(config, form_data)

    selected_provider = form_data.get("llm_provider", "mistral")
    missing_provider_env = _missing_provider_env(selected_provider)
    show_ollama_warning = selected_provider == "ollama" and not os.environ.get(
        "OLLAMA_API_KEY"
    )

    return render_template(
        "settings.html",
        config=config,
        form_data=form_data,
        selected_provider=selected_provider,
        missing_provider_env=missing_provider_env,
        show_ollama_warning=show_ollama_warning,
    )


@web_bp.route("/", methods=["GET"])
def dashboard():
    """Handles the main dashboard page."""
    workspace_path = os.environ.get("WORKSPACE", ".")
    plan_path = os.path.join(workspace_path, "plan.md")
    plan_content = "No plan.md found in workspace."
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_content = f.read()
        except FileExistsError as e:
            logger.error("Error reading plan.md: %s", e)
            plan_content = f"Error reading plan.md: {e}"
    return render_template("index.html", plan_content=plan_content)


@web_bp.route("/settings", methods=["GET", "POST"])
def settings():
    """Handles the settings page."""
    config = AgentConfig.query.first()
    if not config:
        config = AgentConfig(task_system_type="TRELLO", system_config={})

    if request.method == "POST":
        return settings_post(config)

    return settings_get(config)
