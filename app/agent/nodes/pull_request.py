"""Create a pull request node"""

import logging
import subprocess
from typing import Any, Dict

from app.agent.services.summaries import (
    append_agent_summary,
    build_agent_summary_markdown,
)
from app.agent.services.pull_request import create_or_update_pr
from app.agent.state import AgentState
from app.agent.utils import get_codespace, get_current_git_branch
from app.core.config import get_env_settings
from app.core.db_task_utils import update_db_task

logger = logging.getLogger(__name__)


def create_pull_request_node():
    """Create a pull request node"""

    async def pull_request_node(state: AgentState) -> Dict[str, Any]:
        logger.info("--- PULL REQUEST node ---")
        success, summary_entries = _create_or_update_pr(state)
        if success:
            logger.info("Pull request created/updated successfully")
        else:
            logger.error("Pull request creation/update failed")

        return {"agent_summary": summary_entries, "current_node": "pull_request"}

    return pull_request_node


def _append_summary(
    summary_entries: list[str], state: AgentState, title: str, message: str
) -> list[str]:
    summary_entries = append_agent_summary(summary_entries, title, message)
    state["agent_summary"] = summary_entries
    return summary_entries


def _create_or_update_pr(state: AgentState):
    summary_entries = list(state.get("agent_summary") or [])
    has_changes, _ = _execute_git_status()
    failure_detected = False
    failure_reason = "Pull request skipped"

    commit_message = _generate_commit_message(state)
    if not has_changes:
        logger.info("No changes detected, skipping Git workflow")
        failure_detected = True
        failure_reason = "Pull request skipped: no changes detected"
    elif not _execute_git_add():
        logger.error("Git add failed, skipping remaining Git operations")
        failure_detected = True
        failure_reason = "Pull request failed: git add failed"
    elif not _execute_git_commit(commit_message):
        logger.error("Git commit failed, skipping remaining Git operations")
        failure_detected = True
        failure_reason = "Pull request failed: git commit failed"

    if failure_detected:
        summary_entries = _append_summary(summary_entries, state, "PR", failure_reason)
        return False, summary_entries

    push_success, push_msg = _execute_git_push()
    if not push_success:
        logger.error("Git push failed: %s", push_msg)
        failure_reason = f"Pull request failed: git push failed ({push_msg})"
        summary_entries = _append_summary(summary_entries, state, "PR", failure_reason)
        return False, summary_entries

    pr_title, pr_body = _build_pr_inputs(state)
    pr_success, pr_msg, pr_url = create_or_update_pr(
        title=pr_title,
        body=pr_body,
    )
    if not pr_success:
        logger.error("PR creation/update failed: %s", pr_msg)
        summary_entries = _append_summary(
            summary_entries,
            state,
            "PR",
            f"Pull request creation/update failed: {pr_msg}",
        )
        return False, summary_entries

    logger.info("Git workflow completed successfully: %s", pr_msg)
    if not pr_url:
        logger.warning("PR creation succeeded but no URL was returned")
        summary_entries = _append_summary(
            summary_entries,
            state,
            "PR",
            "Pull request missing URL despite success",
        )
        return False, summary_entries

    task_id = state.get("task_id")
    if task_id and pr_url:
        pr_number = _extract_pr_number_from_url(pr_url)
        if pr_number:
            update_db_task(task_id=task_id, pr_number=pr_number, pr_url=pr_url)
            logger.info("Stored PR #%d for task %s", pr_number, task_id)

    summary_entries = _append_summary(
        summary_entries,
        state,
        "PR",
        f"Pull request available at\n\n {pr_url}",
    )
    return True, summary_entries

def _generate_commit_message(state: AgentState) -> str:
    """Generate a concise commit message from the latest agent summary."""
    summaries = state.get("agent_summary") or []
    parsed_entries: list[tuple[str | None, str]] = []

    for entry in summaries:
        role, text = _parse_summary_entry(entry)
        cleaned_text = text.strip()
        if cleaned_text:
            parsed_entries.append((role, cleaned_text))

    summary_text = ""
    summary_role: str | None = None

    for role, text in parsed_entries:
        if (role or "").lower() == "tester":
            continue
        summary_text = text
        summary_role = role
        break

    if not summary_text:
        return "fix: automated test-driven changes"

    prefix_map = {
        "coder": "feat",
        "bugfixer": "fix",
        "analyst": "chore",
    }
    role = (summary_role or state.get("task_role") or "").strip().lower()
    prefix = prefix_map.get(role, "chore")

    first_line = f"{prefix}: {summary_text}"
    if len(first_line) > 75:
        first_line = first_line[:72].rstrip() + "..."

    if role in {"coder", "bugfixer"}:
        role_entries = [
            text
            for entry_role, text in parsed_entries
            if (entry_role or "").lower() == role
        ]
        if len(role_entries) > 1:
            additional_lines = role_entries[1:]
            details = "\n".join(f"- {text}" for text in additional_lines if text)
            if details:
                return f"{first_line}\n\n{details}"

    return first_line

def _parse_summary_entry(entry: str) -> tuple[str | None, str]:
    """Return (role, summary_text) from a formatted summary entry."""
    if not entry:
        return None, ""

    trimmed = entry.strip()
    if trimmed.startswith("**["):
        closing = trimmed.find("]**")
        if closing != -1:
            role = trimmed[3:closing].strip() or None
            summary_text = trimmed[closing + 3 :].strip()
            return (role.lower() if role else None), summary_text

    return None, trimmed


def _extract_pr_number_from_url(pr_url: str) -> int | None:
    """
    Extract the PR number from a GitHub PR URL.

    Args:
        pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)

    Returns:
        The PR number, or None if extraction fails
    """
    try:
        parts = pr_url.rstrip("/").split("/")
        if len(parts) >= 2 and parts[-2] == "pull":
            return int(parts[-1])
    except (ValueError, IndexError):
        pass
    return None


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

    task = state.get("task")
    task_title = task.name
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
        logger.info("Git status check: %s changes found", "Some" if has_changes else "No")
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
    token = get_env_settings().github_token
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
