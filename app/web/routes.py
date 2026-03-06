"""The routes for the web application.

This module uses a Flask Blueprint to organize the routes as thin controllers.
Route handlers delegate business logic to the service layer and focus only on
HTTP request/response handling.
"""

import logging
from dataclasses import asdict

from flask import (
    Blueprint,
    flash,
    jsonify,
    render_template,
    request,
    Response,
)

from app.agent.services.pull_request import (
    fetch_pr_details,
    fetch_pr_reviews,
    fetch_pr_review_comments,
    format_pr_review_message,
    get_latest_pr_review_status,
)
from app.web.services import dashboard_service, settings_service
from app.web.services.dashboard_service import PlanReviewError, process_plan_review

logger = logging.getLogger(__name__)

web_bp = Blueprint("web", __name__, template_folder="templates", static_folder="static")


@web_bp.route("/", methods=["GET"])
def landing():
    """Handles the landing page."""
    return render_template("index.html")


@web_bp.route("/dashboard", methods=["GET"])
async def dashboard():
    """Handles the main dashboard page."""
    context = await dashboard_service.get_template_context()
    return render_template("dashboard.html", **context)


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


@web_bp.route("/api/pr/<owner>/<repo>/<int:pr_number>", methods=["GET"])
def get_pr_json(owner: str, repo: str, pr_number: int):
    """
    Fetch a GitHub PR with its reviews and review comments as JSON.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number

    Returns:
        JSON response with PR details, reviews, and comments
    """
    pr = fetch_pr_details(owner, repo, pr_number)
    if not pr:
        return jsonify({"error": f"PR #{pr_number} not found"}), 404

    reviews = fetch_pr_reviews(pr_number, owner, repo)
    comments = fetch_pr_review_comments(pr_number, owner, repo)

    is_approved, rejection_reviews, _ = get_latest_pr_review_status(pr_number, owner, repo)

    response = {
        "pull_request": asdict(pr),
        "is_approved": is_approved,
        "reviews": [asdict(r) for r in reviews],
        "review_comments": [asdict(c) for c in comments],
        "rejection_reviews": [asdict(r) for r in rejection_reviews],
    }

    return jsonify(response)


@web_bp.route("/api/pr/<owner>/<repo>/<int:pr_number>/formatted", methods=["GET"])
def get_pr_formatted(owner: str, repo: str, pr_number: int):
    """
    Fetch a GitHub PR with its reviews and comments as formatted text.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number

    Returns:
        Plain text response with formatted PR review feedback
    """
    pr = fetch_pr_details(owner, repo, pr_number)
    if not pr:
        return Response(f"PR #{pr_number} not found", status=404, mimetype="text/plain")

    is_approved, rejection_reviews, code_comments = get_latest_pr_review_status(
        pr_number, owner, repo
    )

    lines = [
        f"Pull Request #{pr_number}: {pr.title}",
        f"URL: {pr.html_url}",
        f"State: {pr.state}",
        f"Branch: {pr.head_branch} -> {pr.base_branch}",
        f"Created: {pr.created_at}",
        f"Updated: {pr.updated_at}",
        "",
        "Description:",
        pr.body or "(No description)",
        "",
        f"Review Status: {'APPROVED' if is_approved else 'CHANGES REQUESTED'}",
    ]

    formatted_review = format_pr_review_message(pr.html_url, rejection_reviews, code_comments)
    lines.append(formatted_review)

    return Response("\n".join(lines), mimetype="text/plain")


@web_bp.route("/task/review_plan", methods=["POST"])
async def review_plan():
    """Updates the plan state of the current task."""
    data = request.json or {}
    new_state = data.get("plan_state")
    rejection_reason = data.get("rejection_reason")

    try:
        result = await process_plan_review(new_state, rejection_reason)
        return jsonify(result)
    except PlanReviewError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Unexpected error while updating plan state")
        return jsonify({"error": "Failed to update task"}), 500
