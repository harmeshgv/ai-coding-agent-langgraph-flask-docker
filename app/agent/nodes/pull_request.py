"""Create a pull request node"""

import logging
import os
import subprocess
from typing import Any, Dict

from app.agent.services.summaries import (
    append_agent_summary,
    build_agent_summary_markdown,
)
from app.agent.services.pull_request import create_or_update_pr
from app.agent.state import AgentState
from app.agent.utils import get_codespace, get_current_git_branch

logger = logging.getLogger(__name__)


def create_pull_request_node():
    """Create a pull request node"""

    async def pull_request_node(state: AgentState) -> Dict[str, Any]:
        success, summary_entries = _create_or_update_pr(state)
        if success:
            logger.info("Pull request created successfully")
        else:
            logger.error("Pull request creation failed")

        return {"agent_summary": summary_entries}

    return pull_request_node


def _create_or_update_pr(state: AgentState):
    summary_entries = list(state.get("agent_summary") or [])
    has_changes, _ = _execute_git_status()
    failure_detected = False
    if not has_changes:
        logger.info("No changes detected, skipping Git workflow")
        failure_detected = True
    elif not _execute_git_add():
        logger.error("Git add failed, skipping remaining Git operations")
        failure_detected = True
    elif not _execute_git_commit("fix: automated test-driven changes"):
        logger.error("Git commit failed, skipping remaining Git operations")
        failure_detected = True

    if failure_detected:
        return False, summary_entries

    push_success, push_msg = _execute_git_push()
    if not push_success:
        logger.error("Git push failed: %s", push_msg)
        return False, summary_entries

    pr_title, pr_body = _build_pr_inputs(state)
    pr_success, pr_msg, pr_url = create_or_update_pr(
        title=pr_title,
        body=pr_body,
    )
    if not pr_success:
        logger.error("PR creation failed: %s", pr_msg)
        return False, summary_entries

    logger.info("Git workflow completed successfully: %s", pr_msg)
    if not pr_url:
        logger.warning("PR creation succeeded but no URL was returned")
        return False, summary_entries

    summary_entries = append_agent_summary(
        summary_entries,
        "PR",
        f"Pull request available at\n\n {pr_url}",
    )
    state["agent_summary"] = summary_entries
    return True, summary_entries


def _build_pr_inputs(state: AgentState) -> tuple[str, str]:
    """
    Build the PR title and body using the task name and agent summaries.
    """
    aggregated_summary = build_agent_summary_markdown(
        state,
        heading="## Agent Update",
        bullet_prefix="- ",
        line_separator="\n",
    )
    pr_body_summary = aggregated_summary
    task_title = state.get("task_name") or ""
    pr_title = task_title or "Automated Fix"
    pr_body = "Automated changes after successful tests."
    if pr_body_summary:
        pr_body += f"\n\n{pr_body_summary}"

    return pr_title, pr_body


def _execute_git_status() -> tuple[bool, str]:
    """
    Executes git status and checks if there are changes.
    Returns (has_changes, output).
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=get_codespace(),
            check=True,
            capture_output=True,
            text=True,
        )
        has_changes = bool(result.stdout.strip())
        logger.info(
            "Git status check: %s changes found", "Some" if has_changes else "No"
        )
        return has_changes, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error("Git status failed: %s", e.stderr)
        return False, f"Error: {e.stderr}"


def _execute_git_add() -> bool:
    """
    Adds all changes to staging area.
    Returns True if successful.
    """
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=get_codespace(),
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Git add successful")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Git add failed: %s", e.stderr)
        return False


def _execute_git_commit(message: str) -> bool:
    """
    Commits staged changes with the given message.
    Returns True if successful.
    """
    try:
        subprocess.run(
            ["git", "config", "user.email", "agent@bot.com"],
            cwd=get_codespace(),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Coding Agent"],
            cwd=get_codespace(),
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=get_codespace(),
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Git commit successful: %s", message)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Git commit failed: %s", e.stderr)
        return False


def _execute_git_push() -> tuple[bool, str]:
    """
    Pushes the current branch to origin.
    Returns (success, message).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN missing for git push")
        return False, "ERROR: GITHUB_TOKEN missing"

    try:
        current_branch = get_current_git_branch()
        if not current_branch:
            logger.error("Could not determine current branch")
            return False, "ERROR: Could not determine current branch"

        if current_branch in ["main", "master"]:
            logger.warning("Attempted to push to default branch '%s'", current_branch)
            return False, f"ERROR: Cannot push to default branch '{current_branch}'"

        current_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=get_codespace(),
            text=True,
        ).strip()

        if "https://" in current_url and "@" not in current_url:
            auth_url = current_url.replace("https://", f"https://{token}@")
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=get_codespace(),
                check=True,
            )

        result = subprocess.run(
            ["git", "push", "-u", "origin", "HEAD"],
            cwd=get_codespace(),
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Git push successful")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        safe_stderr = e.stderr.replace(token, "***") if token else e.stderr
        logger.error("Git push failed: %s", safe_stderr)
        return False, f"Push FAILED: {safe_stderr}"
