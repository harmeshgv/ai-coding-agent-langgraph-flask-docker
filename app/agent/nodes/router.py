"""
Defines the router node for the agent graph.

This node is responsible for the initial analysis of a task. It uses a
specialized LLM call to classify the user's request and decide which
specialist agent (e.g., Coder, Bugfixer, Analyst) should handle it next.
"""

import logging
import re
import subprocess
from typing import Dict, Literal

from flask import current_app
from git import Repo
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.state import AgentState
from agent.utils import filter_messages_for_llm, checkout_branch, get_workspace
from core.repositories import get_branch_for_issue, upsert_issue

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You are the Senior Technical Lead.
Your job is to analyze the incoming task and route it to the correct specialist.

OPTIONS:
1. 'coder': For implementing new features, creating new files, or refactoring.
2. 'bugfixer': For fixing errors, debugging, or solving issues in existing code.
3. 'analyst': For explaining code, reviewing architecture, or answering questions (NO code changes).

Respond ONLY with valid JSON that matches {"role":"coder"|"bugfixer"|"analyst"} with no additional text or markdown.
"""

ROLE_PREFIXES = {
    "coder": "feature",
    "bugfixer": "bugfix",
}


class RouterDecision(BaseModel):
    """Classify the incoming task into the correct category."""

    role: Literal["coder", "bugfixer", "analyst"] = Field(
        ..., description="The specific role needed to solve the task."
    )


def create_router_node(sys_config: dict, llm):
    """
    Factory function that creates the router node for the agent graph.

    Args:
        sys_config: The system configuration.        
        llm: The language model to be used for routing decisions.

    Returns:
        A function that represents the router node.
    """
    structured_llm = llm.with_structured_output(RouterDecision)

    async def router_node(state: AgentState) -> Dict[str, str]:
        # Router only needs the original task to make routing decision
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=3)
        base_messages = [SystemMessage(content=ROUTER_SYSTEM)] + filtered_messages
        current_messages = list(base_messages)

        for attempt in range(3):
            try:
                response = await structured_llm.ainvoke(current_messages)
                logger.info("Router decided: %s", response.role)

                trello_card_id = state["trello_card_id"]
                trello_card_name = state.get("trello_card_name", "")
                if trello_card_id:
                    await checkout_card_branch(
                        trello_card_id,
                        trello_card_name,
                        response.role,
                        sys_config
                    )
                else:
                    raise ValueError("Missing trello_card_id in AgentState")

                return {"next_step": response.role}
            except OutputParserException as exc:
                logger.warning(
                    "Router invalid JSON attempt %d/3: %s",
                    attempt + 1,
                    exc,
                    exc_info=True,
                )
                correction = HumanMessage(
                    content=(
                        "STOP. Respond ONLY with compact JSON like "
                        '{"role":"coder"} and no other text.'
                    )
                )
                current_messages.append(correction)

        logger.error("Router failed to produce valid JSON after retries.")
        raise RuntimeError("Router failed to produce valid JSON after 3 retries.")

    return router_node


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

async def checkout_card_branch(card_id: str, card_name: str, role: str, sys_config: dict):
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


def _slugify(value: str | None) -> str:
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


async def checkout_branch_for_card(card_id: str, card_name: str, role: str, sys_config: dict):
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
        logger.warning(
            "Failed to persist branch mapping for card %s: %s", card_id, exc
        )

    real_git_branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=get_workspace(),
        text=True,
    ).strip()
    logger.info("Current branch after checkout: %s", real_git_branch)
