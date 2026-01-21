"""The routes for the web application.

This module uses a Flask Blueprint to organize the routes as thin controllers.
Route handlers delegate business logic to the service layer and focus only on
HTTP request/response handling.
"""

import logging

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.web.services.dashboard_service import DashboardService
from app.web.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

web_bp = Blueprint(
    "web", __name__, template_folder="templates", static_folder="../static"
)


@web_bp.route("/", methods=["GET"])
def dashboard():
    """Handles the main dashboard page."""
    context = DashboardService.get_template_context()
    return render_template("index.html", **context)


@web_bp.route("/settings", methods=["GET", "POST"])
def settings():
    """Handles the settings page."""
    config = SettingsService.get_or_create_config()

    if request.method == "POST":
        success, error_msg = SettingsService.validate_and_save(config)
        if success:
            flash("Settings saved successfully!", "success")
        else:
            flash(f"Error saving settings: {error_msg}", "danger")
        return redirect(url_for("web.settings"))

    context = SettingsService.get_template_context(config)
    return render_template("settings.html", **context)
