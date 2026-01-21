"""Service for GitHub Pull Request operations."""

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional

import requests

from app.agent.utils import get_codespace, get_current_git_branch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PullRequest:  # pylint: disable=too-many-instance-attributes
    """Represents a GitHub Pull Request."""

    number: int
    title: str
    body: str
    html_url: str
    state: str
    head_branch: str
    base_branch: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class GitHubContext:
    """Holds repository metadata required for PR operations."""

    owner: str
    repo: str
    branch: str
    headers: Dict[str, str]


def get_latest_open_pr_for_branch(branch_name: str) -> Optional[PullRequest]:
    """
    Get the latest open pull request for the given branch.

    Args:
        branch_name: The name of the branch to check

    Returns:
        PullRequest object if an open PR exists, None otherwise
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set, cannot fetch PR")
        return None

    try:
        owner, repo = get_github_repo_info()
        if not owner or not repo:
            logger.warning("Could not determine GitHub owner/repo")
            return None

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        params = {"head": f"{owner}:{branch_name}", "state": "open"}

        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            pulls = response.json()
            if pulls:
                pr_data = pulls[0]
                pr = PullRequest(
                    number=pr_data["number"],
                    title=pr_data["title"],
                    body=pr_data.get("body", ""),
                    html_url=pr_data["html_url"],
                    state=pr_data["state"],
                    head_branch=pr_data["head"]["ref"],
                    base_branch=pr_data["base"]["ref"],
                    created_at=pr_data["created_at"],
                    updated_at=pr_data["updated_at"],
                )
                logger.info(
                    "Found PR #%d for branch '%s': %s",
                    pr.number,
                    branch_name,
                    pr.title
                )
                return pr

            logger.info("No open PR found for branch '%s'", branch_name)
            return None

        logger.warning(
            "PR fetch failed with status %d: %s",
            response.status_code,
            response.text
        )
        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error fetching PR for branch '%s': %s", branch_name, e)
        return None


def check_pr_exists_for_branch(branch_name: str) -> bool:
    """
    Check if a pull request exists for the given branch.

    Args:
        branch_name: The name of the branch to check

    Returns:
        True if a PR exists for this branch, False otherwise
    """
    return get_latest_open_pr_for_branch(branch_name) is not None


def create_or_update_pr(title: str, body: str) -> tuple[bool, str, Optional[str]]:
    """
    Creates or updates a GitHub Pull Request.

    Args:
        title: PR title
        body: PR body/description

    Returns:
        Tuple of (success, message, pr_url)
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN missing for PR creation")
        return False, "ERROR: GITHUB_TOKEN missing", None

    try:
        context = build_github_context(token)
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
                return update_existing_pr(context, pulls[0], body)

        return create_new_pr(context, title, body)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("PR creation failed: %s", str(e))
        return False, f"ERROR: {str(e)}", None


def update_existing_pr(
    context: GitHubContext,
    pr_data: dict,
    body: str,
) -> tuple[bool, str, Optional[str]]:
    """
    Add comment to existing PR.

    Args:
        context: GitHub context with auth headers
        pr_data: Existing PR data from API
        body: Comment body to add

    Returns:
        Tuple of (success, message, pr_url)
    """
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


def create_new_pr(
    context: GitHubContext,
    title: str,
    body: str,
) -> tuple[bool, str, Optional[str]]:
    """
    Create new PR.

    Args:
        context: GitHub context with auth headers
        title: PR title
        body: PR description

    Returns:
        Tuple of (success, message, pr_url)
    """
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


def build_github_context(token: str) -> Optional[GitHubContext]:
    """
    Assemble the metadata required to interact with the GitHub API.

    Args:
        token: GitHub API token

    Returns:
        GitHubContext if successful, None otherwise
    """
    owner, repo, current_branch = get_github_repo_info_with_branch()
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


def get_github_repo_info() -> tuple[Optional[str], Optional[str]]:
    """
    Get GitHub owner and repo from git remote.

    Returns:
        Tuple of (owner, repo)
    """
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=get_codespace(),
            text=True,
        ).strip()

        match = re.search(r"github\.com[:/](.+)/(.+?)(\.git)?$", remote_url)
        if not match:
            return None, None

        owner, repo = match.group(1), match.group(2)
        return owner, repo
    except subprocess.CalledProcessError:
        return None, None


def get_github_repo_info_with_branch() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Get GitHub owner, repo, and current branch.

    Returns:
        Tuple of (owner, repo, branch)
    """
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
        current_branch = get_current_git_branch()

        if not current_branch:
            return None, None, None

        return owner, repo, current_branch
    except subprocess.CalledProcessError:
        return None, None, None
