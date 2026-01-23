"""The routes for the web application.

This module uses a Flask Blueprint to organize the routes as thin controllers.
Route handlers delegate business logic to the service layer and focus only on
HTTP request/response handling.
"""

import logging

from flask import (
    Blueprint,
    flash,
    render_template,
    request,
)

from app.web.services import dashboard_service, settings_service

logger = logging.getLogger(__name__)

web_bp = Blueprint(
    "web", __name__, template_folder="templates", static_folder="../static"
)


@web_bp.route("/", methods=["GET"])
def dashboard():
    """Handles the main dashboard page."""
    context = dashboard_service.get_template_context()
    return render_template("index.html", **context)


@web_bp.route("/settings", methods=["GET", "POST"])
def settings():
    """Handles the settings page."""
    agent_settings = settings_service.get_or_create_settings()

    if request.method == "POST":
        success, error_msg = settings_service.validate_and_save(agent_settings)
        if success:
            flash("Settings saved successfully!", "success")
        else:
            flash(f"Error saving settings: {error_msg}", "danger")
        # Re-fetch settings to show updated values
        agent_settings = settings_service.get_or_create_settings()

    context = settings_service.get_template_context(agent_settings)
    return render_template("settings.html", **context)
