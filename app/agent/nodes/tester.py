"""
Defines the Tester agent node for the agent graph.

The Tester is a specialist agent responsible for verifying code changes,
running tests, and reporting the results.
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional
import requests

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from agent.state import AgentState
from agent.tools.local_tools import report_test_result
from agent.utils import (
    append_agent_summary,
    build_agent_summary_markdown,
    filter_messages_for_llm,
    get_workspace,
    load_system_prompt,
    log_agent_response,
)

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


class TesterResult(BaseModel):
    """Call this tool ONLY when you have completed the testing process."""

    result: Literal["pass", "fail"] = Field(
        ...,
        description="The final result. 'pass' if tests and PR are successful, 'fail' otherwise.",
    )
    summary: str = Field(
        ...,
        description="A short summary of what happened (e.g. 'PR created at xyz' "
        + "or 'Tests failed because of NPE').",
    )


def create_tester_node(llm, tools, agent_stack):
    """
    Factory function that creates the Tester agent node.

    Args:
        llm: The language model to be used by the tester.
        tools: A list of tools available to the tester.
        agent_stack: The technology stack to load the correct system prompt.

    Returns:
        A function that represents the tester node.
    """
    sys_msg = load_system_prompt(agent_stack, "tester")
    llm_with_tools = llm.bind_tools(tools + [report_test_result])

    async def tester_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 15 messages)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages = [SystemMessage(content=sys_msg)] + filtered_messages

        # LLM Aufruf
        response = await llm_with_tools.ainvoke(current_messages)

        has_content = bool(response.content)
        has_tool_calls = bool(getattr(response, "tool_calls", []))

        if has_content or has_tool_calls:
            log_agent_response("tester", response)

        report_args = _get_report_result_args(response)
        summary_updated = False
        updated_summary = None
        if tests_passed(report_args):
            summary_updated, updated_summary = _process_successful_tests(state, report_args)

        result: dict[str, Any] = {"messages": [response]}
        if summary_updated:
            result["agent_summary"] = updated_summary
        return result

    return tester_node


def _process_successful_tests(
    state: AgentState,
    report_args: Dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Run the Git workflow and PR creation steps after successful tests.
    Returns (updated_flag, summary_entries) where updated_flag is True when the
    agent_summary gains new information (e.g., PR link recorded).
    """
    summary = report_args.get("summary", "")
    detail = f": {summary}" if summary else ""
    logger.info("Tester node reported PASS result%s", detail)

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

    pr_title, pr_body = _build_pr_inputs(state, summary)
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
        "tester",
        f"Pull request available at {pr_url}",
    )
    state["agent_summary"] = summary_entries
    return True, summary_entries


def _build_pr_inputs(state: AgentState, summary: str) -> tuple[str, str]:
    """
    Build the PR title and body using the Trello card name and agent summaries.
    """
    aggregated_summary = build_agent_summary_markdown(
        state,
        heading="## Agent Update",
        bullet_prefix="- ",
        line_separator="\n",
    )
    pr_body_summary = aggregated_summary or summary
    issue_title = state.get("trello_card_name") or ""
    pr_title = issue_title or "Automated Fix"
    pr_body = "Automated changes after successful tests."
    if pr_body_summary:
        pr_body += f"\n\n{pr_body_summary}"

    return pr_title, pr_body


def _get_report_result_args(response: Any) -> Optional[Dict[str, Any]]:
    """
    Returns the argument payload of the report_test_result tool call if present.
    """
    for tool_call in getattr(response, "tool_calls", []) or []:
        if tool_call.get("name") == "report_test_result":
            return tool_call.get("args", {})
    return None


def tests_passed(tool_args: Optional[Dict[str, Any]]) -> bool:
    """
    Determines whether the provided tool arguments represent a passing test run.
    """
    if not tool_args:
        return False
    result = tool_args.get("result")
    return isinstance(result, str) and result.lower() == "pass"


def _execute_git_status() -> tuple[bool, str]:
    """
    Executes git status and checks if there are changes.
    Returns (has_changes, output).
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=get_workspace(),
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
            cwd=get_workspace(),
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
            cwd=get_workspace(),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Coding Agent"],
            cwd=get_workspace(),
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=get_workspace(),
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
            cwd=get_workspace(),
            text=True,
        ).strip()

        if current_branch in ["main", "master"]:
            logger.warning("Attempted to push to default branch '%s'", current_branch)
            return False, f"ERROR: Cannot push to default branch '{current_branch}'"

        current_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=get_workspace(),
            text=True,
        ).strip()

        if "https://" in current_url and "@" not in current_url:
            auth_url = current_url.replace("https://", f"https://{token}@")
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=get_workspace(),
                check=True,
            )

        result = subprocess.run(
            ["git", "push", "-u", "origin", "HEAD"],
            cwd=get_workspace(),
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
            cwd=get_workspace(),
            text=True,
        ).strip()

        match = re.search(r"github\.com[:/](.+)/(.+?)(\.git)?$", remote_url)
        if not match:
            return None, None, None

        owner, repo = match.group(1), match.group(2)

        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_workspace(),
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


def _execute_create_pull_request(title: str, body: str) -> tuple[bool, str, Optional[str]]:
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
            return False, "ERROR: You are on main/master. Create a feature branch first!", None

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
