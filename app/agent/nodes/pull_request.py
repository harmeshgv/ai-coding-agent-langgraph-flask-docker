"""Create a pull request node"""

import logging
from typing import Any, Dict

from app.agent.services.git_workspace import (
    commit as git_commit,
    has_changes as git_has_changes,
    push as git_push,
    stage_all as git_stage_all,
)
from app.agent.services.summaries import (
    append_agent_summary,
    build_agent_summary_markdown,
)
from app.agent.services.pull_request import create_or_update_pr
from app.agent.state import AgentState, TaskType
from app.agent.utils import get_workspace
from app.core.config import get_env_settings
from app.core.localdb.agent_tasks_utils import update_db_task

logger = logging.getLogger(__name__)



ROLE_PREFIX_MAP = {
    TaskType.CODING: "feat",
    TaskType.BUGFIXING: "fix",
    TaskType.ANALYZING: "chore",
    TaskType.UNKNOWN: "chore",
}


def create_pull_request_node():
    """Create a pull request node"""

    async def pull_request_node(state: AgentState) -> Dict[str, Any]:
        if state["current_node"] != "pull_request":
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

    has_changes = git_has_changes(get_workspace())
    logger.info("Git status check: %s changes found", "Some" if has_changes else "No")

    failure_detected = False
    failure_reason = "Pull request skipped"

    commit_message = _generate_commit_message(state)
    if not has_changes:
        logger.info("No changes detected, skipping Git workflow")
        failure_detected = True
        failure_reason = "Pull request skipped: no changes detected"
    elif not git_stage_all(work_dir=get_workspace()):
        logger.error("Git add failed, skipping remaining Git operations")
        failure_detected = True
        failure_reason = "Pull request failed: git add failed"
    elif not git_commit(work_dir=get_workspace(), message=commit_message):
        logger.error("Git commit failed, skipping remaining Git operations")
        failure_detected = True
        failure_reason = "Pull request failed: git commit failed"

    if failure_detected:
        summary_entries = _append_summary(summary_entries, state, "PR", failure_reason)
        return False, summary_entries

    push_success, push_msg = git_push(
        work_dir=get_workspace(), token=get_env_settings().github_token
    )
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

    task_id = state.get("provider_task").id if state.get("provider_task") else None
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

    task_type = TaskType.from_string(
        state.get("agent_task").task_type if state.get("agent_task") else ""
    )
    prefix = ROLE_PREFIX_MAP.get(task_type, "chore")

    first_line = f"{prefix}: {summary_text}"
    if len(first_line) > 75:
        first_line = first_line[:72].rstrip() + "..."

    if task_type in {TaskType.CODING, TaskType.BUGFIXING} and summary_role:
        role_entries = [
            text
            for entry_role, text in parsed_entries
            if (entry_role or "").lower() == summary_role
        ]
        details = _build_role_details(role_entries)
        if details:
            return f"{first_line}\n\n{details}"

    return first_line


def _build_role_details(role_entries: list[str]) -> str | None:
    """Return formatted detail bullet list for role entries."""
    if len(role_entries) <= 1:
        return None

    filtered_entries: list[str] = []
    previous_text: str | None = None
    for current_text in role_entries:
        if current_text and current_text != previous_text:
            filtered_entries.append(current_text)
        previous_text = current_text

    if not filtered_entries:
        return None

    return "\n".join(f"- {text}" for text in filtered_entries)


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

    task = state.get("provider_task")
    task_title = task.name
    pr_title = task_title or "Automated Fix"
    pr_body = "Automated changes after successful tests."
    if pr_body_summary:
        pr_body += f"\n\n{pr_body_summary}"

    return pr_title, pr_body
