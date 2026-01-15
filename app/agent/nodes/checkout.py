"""Create a checkout node"""

import logging
import re
import subprocess
from typing import Any, Dict

from core.trello_repository import get_branch_for_issue, upsert_issue
from flask import current_app
from git import Repo

from agent.services.git_workspace import checkout_branch
from agent.state import AgentState
from agent.utils import get_workspace

logger = logging.getLogger(__name__)

ROLE_PREFIXES = {
    "coder": "feature",
    "bugfixer": "bugfix",
}


def create_checkout_node(sys_config: dict):
    """Create a checkout node"""

    async def checkout_node(state: AgentState) -> Dict[str, Any]:  # pylint: disable=unused-argument
        trello_card_id = state["trello_card_id"]
        trello_card_name = state["trello_card_name"]

        if trello_card_id and trello_card_name:
            await checkout_card_branch(
                trello_card_id, trello_card_name, "coder", sys_config
            )
        else:
            raise ValueError("Missing trello_card_id or trello_card_name in AgentState")

        return {}

    return checkout_node


async def checkout_card_branch(
    card_id: str, card_name: str, role: str, sys_config: dict
):
    """
    Checks out the existing git branch for a Trello card from the database.
    """

    if role not in ["coder", "bugfixer"]:
        repo = Repo(get_workspace())
        repo.git.fetch()
        repo.git.reset("--hard")
        return

    git_branch = await get_existing_branch_for_card(card_id)

    if not git_branch:
        logger.info("No git branch found for card %s", card_id)
        await checkout_branch_for_card(card_id, card_name, role, sys_config)
    else:
        logger.info(
            "Checking out existing git branch: %s for card %s - %s",
            git_branch,
            card_id,
            card_name,
        )

        github_repo_url = sys_config.get("github_repo_url")
        if github_repo_url:
            checkout_branch(github_repo_url, git_branch, get_workspace())
        else:
            logger.warning("No github_repo_url configured, skipping checkout")

        real_git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_workspace(),
            text=True,
        ).strip()
        logger.info("Current branch: %s", real_git_branch)


async def get_existing_branch_for_card(card_id: str):
    """
    Retrieves the existing git branch for a Trello card from the database.
    Returns None if no branch exists for this card.
    """
    try:
        with current_app.app_context():
            branch_name = get_branch_for_issue(card_id)
            return branch_name
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to retrieve branch for card %s: %s", card_id, e)
        return None


def _slugify(value: str | None) -> str:
    """
    Convert a string to a branch-friendly slug.
    """
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def _build_base_branch_name(card_id: str, card_name: str, role: str) -> str:
    slug = _slugify(card_name)
    sanitized_card_id = re.sub(r"[^a-z0-9]", "", card_id.lower())
    short_id = sanitized_card_id[:8] if sanitized_card_id else "card"
    branch_suffix = slug[:48] if slug else "update"
    role_prefix = ROLE_PREFIXES.get(role, "task")
    return f"agent/{role_prefix}/{short_id}-{branch_suffix}"


def _collect_branch_names(repo: Repo) -> set[str]:
    names = {head.name for head in repo.heads}
    for remote in repo.remotes:
        for ref in remote.refs:
            remote_name = getattr(ref, "remote_head", None)
            if remote_name:
                names.add(remote_name)
            else:
                names.add(ref.name.split("/")[-1])
    return names


def _resolve_unique_branch_name(base_name: str, existing_names: set[str]) -> str:
    candidate = base_name
    suffix_counter = 1
    while candidate in existing_names:
        candidate = f"{base_name}-{suffix_counter}"
        suffix_counter += 1
    if candidate != base_name:
        logger.info(
            "Branch name conflict detected. Using '%s' instead of '%s'.",
            candidate,
            base_name,
        )
    return candidate


async def checkout_branch_for_card(
    card_id: str, card_name: str, role: str, sys_config: dict
):
    """
    Checks out a new git branch for an issue.
    The branch name is derived from the card name and guaranteed to be unique.
    Includes role-specific prefixes for clarity.
    """
    if not card_id or not card_name:
        raise ValueError("card_id and card_name are required to create a git branch.")

    repo = Repo(get_workspace())
    repo.git.reset("--hard")
    repo.git.fetch("--prune")

    base_branch_name = _build_base_branch_name(card_id, card_name, role)
    existing_branches = _collect_branch_names(repo)
    branch_name = _resolve_unique_branch_name(base_branch_name, existing_branches)

    github_repo_url = sys_config.get("github_repo_url")
    if not github_repo_url:
        logger.warning(
            "github_repo_url missing in sys_config; cannot checkout branch for card %s",
            card_id,
        )
        return

    logger.info(
        "Creating git branch '%s' for card %s - %s",
        branch_name,
        card_id,
        card_name,
    )

    repo.git.reset("--hard")
    repo.git.checkout("-b", branch_name)

    try:
        with current_app.app_context():
            upsert_issue(card_id, card_name, branch_name, github_repo_url)
            logger.info(
                "Persisted branch '%s' for card %s in database", branch_name, card_id
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to persist branch mapping for card %s: %s", card_id, exc)

    real_git_branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=get_workspace(),
        text=True,
    ).strip()
    logger.info("Current branch after checkout: %s", real_git_branch)
