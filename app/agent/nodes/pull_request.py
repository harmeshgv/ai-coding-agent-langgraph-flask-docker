"""Create a pull request node"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from agent.services.summaries import (
    append_agent_summary,
    build_agent_summary_markdown,
)
from agent.state import AgentState
from agent.utils import get_codespace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubContext:
    """
    Holds repository metadata required for PR operations.
    """

    owner: str
    repo: str
    branch: str
    headers: Dict[str, str]


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
    pr_success, pr_msg, pr_url = _execute_create_pull_request(
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
    Build the PR title and body using the Trello card name and agent summaries.
    """
    aggregated_summary = build_agent_summary_markdown(
        state,
        heading="## Agent Update",
        bullet_prefix="- ",
        line_separator="\n",
    )
    pr_body_summary = aggregated_summary
    issue_title = state.get("trello_card_name") or ""
    pr_title = issue_title or "Automated Fix"
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
        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_codespace(),
            text=True,
        ).strip()

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


def _get_github_repo_info() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get GitHub owner, repo, and current branch. Returns (owner, repo, branch)."""
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=get_codespace(),
            text=True,
        ).strip()

        match = re.search(r"github\.com[:/](.+)/(.+?)(\.git)?$", remote_url)
        if not match:
            return None, None, None

        owner, repo = match.group(1), match.group(2)

        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_codespace(),
            text=True,
        ).strip()

        return owner, repo, current_branch
    except subprocess.CalledProcessError:
        return None, None, None


def _build_github_context(token: str) -> Optional[GitHubContext]:
    """
    Assemble the metadata required to interact with the GitHub API.
    """
    owner, repo, current_branch = _get_github_repo_info()
    if not owner or not repo or not current_branch:
        logger.error("Could not parse GitHub repository information")
        return None

    headers: Dict[str, str] = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    return GitHubContext(
        owner=owner,
        repo=repo,
        branch=current_branch,
        headers=headers,
    )


def _update_existing_pr(
    context: GitHubContext,
    pr_data: dict,
    body: str,
) -> tuple[bool, str, Optional[str]]:
    """Add comment to existing PR. Returns (success, message, pr_url)."""
    pr_number = pr_data.get("number")
    pr_url = pr_data.get("html_url")
    comment_url = (
        f"https://api.github.com/repos/{context.owner}/{context.repo}/issues/"
        f"{pr_number}/comments"
    )
    comment_payload = {"body": f"**Automated Update:**\n\n{body}"}

    response = requests.post(
        comment_url,
        json=comment_payload,
        headers=context.headers,
        timeout=10,
    )

    if response.status_code == 201:
        logger.info("Added comment to existing PR: %s", pr_url)
        return True, f"SUCCESS: Added comment to existing PR: {pr_url}", pr_url
    return False, f"ERROR adding comment: {response.status_code}", pr_url


def _create_new_pr(
    context: GitHubContext,
    title: str,
    body: str,
) -> tuple[bool, str, Optional[str]]:
    """Create new PR. Returns (success, message, pr_url)."""
    url = f"https://api.github.com/repos/{context.owner}/{context.repo}/pulls"
    payload = {"title": title, "body": body, "head": context.branch, "base": "main"}
    response = requests.post(url, json=payload, headers=context.headers, timeout=10)

    if response.status_code == 422:
        logger.info("Target 'main' not found, trying 'master'...")
        payload["base"] = "master"
        response = requests.post(url, json=payload, headers=context.headers, timeout=10)

    if response.status_code == 201:
        pr_url = response.json().get("html_url")
        logger.info("Pull Request created: %s", pr_url)
        return True, f"SUCCESS: Pull Request created: {pr_url}", pr_url

    return False, f"ERROR creating PR: {response.status_code} - {response.text}", None


def _execute_create_pull_request(
    title: str, body: str
) -> tuple[bool, str, Optional[str]]:
    """
    Creates or updates a GitHub Pull Request.
    Returns (success, message, pr_url).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN missing for PR creation")
        return False, "ERROR: GITHUB_TOKEN missing", None

    try:
        context = _build_github_context(token)
        if not context:
            return False, "ERROR: Missing GitHub context", None

        if context.branch in ["main", "master"]:
            return (
                False,
                "ERROR: You are on main/master. Create a feature branch first!",
                None,
            )

        url = f"https://api.github.com/repos/{context.owner}/{context.repo}/pulls"
        params = {"head": f"{context.owner}:{context.branch}", "state": "open"}
        response = requests.get(url, headers=context.headers, params=params, timeout=10)

        if response.status_code == 200:
            pulls = response.json()
            if pulls:
                return _update_existing_pr(context, pulls[0], body)

        return _create_new_pr(context, title, body)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("PR creation failed: %s", str(e))
        return False, f"ERROR: {str(e)}", None
