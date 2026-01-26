"""Create a checkout node"""

import logging
import re
import subprocess
from typing import Any, Dict, Optional

from flask import current_app
from git import Repo

from app.agent.integrations.board_provider import BoardTask
from app.agent.services.git_workspace import checkout_branch
from app.agent.services.tasks_services import save_task_in_db
from app.agent.state import AgentState
from app.agent.utils import get_codespace
from app.core.models import AgentSettings
from app.core.task_repository import get_branch_for_task

logger = logging.getLogger(__name__)

ROLE_PREFIXES = {
    "coder": "feature",
    "bugfixer": "bugfix",
}


def create_checkout_node(agent_settings: AgentSettings):
    """Create a checkout node"""

    async def checkout_node(state: AgentState) -> Dict[str, Any]:  # pylint: disable=unused-argument
        task: Optional[BoardTask] = state["task"] if state["task"] else None

        if task:
            await checkout_task_branch(
                task.id,
                task.name,
                "coder",
                agent_settings,
            )
        else:
            raise ValueError("Missing task_id or task_name in AgentState")

        return {"current_node": "checkout"}

    return checkout_node


async def checkout_task_branch(
    task_id: str, task_name: str, role: str, agent_settings: AgentSettings
):
    """
    Checks out the existing git branch for a task from the database.
    """

    if role not in ["coder", "bugfixer"]:
        repo = Repo(get_codespace())
        repo.git.fetch()
        repo.git.reset("--hard")
        return

    git_branch = await get_existing_branch_for_task(task_id)

    if not git_branch:
        logger.info("No git branch found for task %s", task_id)
        await checkout_branch_for_task(task_id, task_name, role, agent_settings)
    else:
        logger.info(
            "Checking out existing git branch: %s for task %s - %s",
            git_branch,
            task_id,
            task_name,
        )

        github_repo_url = agent_settings.github_repo_url
        if github_repo_url:
            checkout_branch(github_repo_url, git_branch, get_codespace())
        else:
            logger.warning("No github_repo_url configured, skipping checkout")

        real_git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_codespace(),
            text=True,
        ).strip()
        logger.info("Current branch: %s", real_git_branch)


async def get_existing_branch_for_task(task_id: str):
    """
    Retrieves the existing git branch for a task from the database.
    Returns None if no branch exists for this task.
    """
    try:
        with current_app.app_context():
            branch_name = get_branch_for_task(task_id)
            return branch_name
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to retrieve branch for task %s: %s", task_id, e)
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


def _build_base_branch_name(task_id: str, task_name: str, role: str) -> str:
    slug = _slugify(task_name)
    sanitized_task_id = re.sub(r"[^a-z0-9]", "", task_id.lower())
    short_id = sanitized_task_id[:8] if sanitized_task_id else "task"
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


async def checkout_branch_for_task(
    task_id: str, task_name: str, role: str, agent_settings: AgentSettings
):
    """
    Checks out a new git branch for a task.
    The branch name is derived from the task name and guaranteed to be unique.
    Includes role-specific prefixes for clarity.
    """
    if not task_id or not task_name:
        raise ValueError("task_id and task_name are required to create a git branch.")

    repo = Repo(get_codespace())
    repo.git.reset("--hard")
    repo.git.fetch("--prune")

    base_branch_name = _build_base_branch_name(task_id, task_name, role)
    existing_branches = _collect_branch_names(repo)
    branch_name = _resolve_unique_branch_name(base_branch_name, existing_branches)

    github_repo_url = agent_settings.github_repo_url
    if not github_repo_url:
        logger.warning(
            "github_repo_url missing in agent settings; cannot checkout branch for task %s",
            task_id,
        )
        return

    logger.info(
        "Creating git branch '%s' for task %s - %s",
        branch_name,
        task_id,
        task_name,
    )

    repo.git.reset("--hard")
    repo.git.checkout("-b", branch_name)

    save_task_in_db(task_id, task_name, branch_name, github_repo_url)

    real_git_branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=get_codespace(),
        text=True,
    ).strip()
    logger.info("Current branch after checkout: %s", real_git_branch)
