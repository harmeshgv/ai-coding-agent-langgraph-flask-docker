"""Helpers for cloning, cleaning, and managing the workspace Git repository."""

from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Optional
from urllib.parse import urlparse, urlunparse

from git import Repo
from git.exc import GitCommandError

logger = logging.getLogger(__name__)

__all__ = [
    "checkout_branch",
    "commit",
    "configure_user",
    "ensure_repository_exists",
    "get_current_branch",
    "get_remote_url",
    "has_changes",
    "normalize_git_url",
    "parse_github_owner_repo",
    "stage_all",
]


def normalize_git_url(url: str) -> str:
    """Normalize a Git URL by stripping credentials for comparison."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        port = parsed.port or ""
        normalized = parsed._replace(netloc=f"{hostname}:{port}")
        return urlunparse(normalized)
    except Exception:  # pylint: disable=broad-exception-caught
        return url.split("@")[-1] if "@" in url else url


def ensure_repository_exists(repo_url: str, work_dir: str) -> None:
    """Ensure work_dir contains a clean checkout of repo_url."""

    def clean_and_clone() -> None:
        for filename in os.listdir(work_dir):
            file_path = os.path.join(work_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to delete %s. Reason: %s", file_path, exc)
        logger.info("Cloning repository %s into %s", repo_url, work_dir)
        Repo.clone_from(repo_url, work_dir)

    if not os.path.isdir(work_dir):
        logger.info("Work directory %s does not exist, creating...", work_dir)
        os.makedirs(work_dir)
    git_dir = os.path.join(work_dir, ".git")
    if not os.path.isdir(git_dir):
        logger.info("No git repository found in %s, cloning...", work_dir)
        clean_and_clone()
        return

    try:
        repo = Repo(work_dir)

        try:
            origin_url = repo.remotes.origin.url
        except AttributeError:
            logger.warning("No origin remote found in %s, re-cloning...", work_dir)
            clean_and_clone()
            return

        normalized_origin = normalize_git_url(origin_url)
        normalized_requested = normalize_git_url(repo_url)

        if normalized_origin != normalized_requested:
            logger.info(
                "Different repository detected (current: %s, requested: %s), re-cloning...",
                normalized_origin,
                normalized_requested,
            )
            clean_and_clone()
            return

        logger.info(
            "Repository %s already exists in %s, updating...", repo_url, work_dir
        )

        if repo.is_dirty(untracked_files=True):
            logger.info("Committing local changes...")
            repo.git.add(A=True)
            repo.index.commit("Auto-commit: local changes before fetch")

        logger.info("Fetching origin...")
        repo.remotes.origin.fetch()

        try:
            default_branch = repo.remotes.origin.refs.HEAD.ref.name.replace(
                "origin/", ""
            )
            logger.info("Checking out default branch: %s", default_branch)
            repo.git.checkout(default_branch)
            repo.git.reset("--hard", f"origin/{default_branch}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Could not checkout default branch: %s, staying on current branch", exc
            )

        logger.info("Repository is ready with clean checkout")

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(
            "Error managing repository in %s: %s, re-cloning...", work_dir, exc
        )
        clean_and_clone()


def checkout_branch(repo_url: str, branch_name: str, work_dir: str) -> None:
    """Ensure branch_name exists locally, fetching or creating as needed."""
    if not branch_name:
        raise ValueError("branch_name is required to checkout a branch.")

    if not os.path.isdir(os.path.join(work_dir, ".git")):
        raise RuntimeError(
            f"No git repository found in {work_dir}. Run ensure_repository_exists first."
        )

    try:
        repo = Repo(work_dir)
    except Exception as exc:
        logger.error("Failed to load repository at %s: %s", work_dir, exc)
        raise

    try:
        if branch_name in repo.heads:
            logger.info("Checking out existing local branch '%s'.", branch_name)
            repo.git.checkout(branch_name)
            return

        logger.info(
            "Local branch '%s' not found. Fetching from origin for repository %s.",
            branch_name,
            repo_url,
        )
        repo.remotes.origin.fetch(branch_name)
        remote_ref = f"origin/{branch_name}"
        if remote_ref in repo.refs:
            repo.git.checkout("-b", branch_name, remote_ref)
            logger.info("Checked out tracking branch '%s' from origin.", branch_name)
            return

        logger.info(
            "Remote branch '%s' not found. Creating new local branch '%s' from current HEAD.",
            remote_ref,
            branch_name,
        )
        repo.git.checkout("-b", branch_name)
        logger.info("Created new local branch '%s'.", branch_name)
    except GitCommandError as exc:
        logger.error("Failed to checkout branch '%s': %s", branch_name, exc)
        raise


def get_current_branch(work_dir: str) -> Optional[str]:
    """Return the name of the currently checked-out branch, or ``None`` on failure."""
    try:
        repo = Repo(work_dir)
        return repo.active_branch.name
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def has_changes(work_dir: str) -> bool:
    """Return ``True`` when the working tree contains staged, unstaged, or untracked changes."""
    try:
        repo = Repo(work_dir)
        return repo.is_dirty(untracked_files=True)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.error("Failed to check git status in %s", work_dir)
        return False


def stage_all(work_dir: str) -> bool:
    """Stage all changes (tracked and untracked) in *work_dir*. Returns success flag."""
    try:
        repo = Repo(work_dir)
        repo.git.add(A=True)
        logger.info("Git add successful")
        return True
    except GitCommandError as exc:
        logger.error("Git add failed: %s", exc)
        return False


def configure_user(work_dir: str, name: str = "Coding Agent", email: str = "agent@bot.com") -> None:
    """Set local ``user.name`` and ``user.email`` on the repository."""
    try:
        repo = Repo(work_dir)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", name)
            cw.set_value("user", "email", email)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to configure git user in %s: %s", work_dir, exc)
        raise


def commit(work_dir: str, message: str) -> bool:
    """Commit staged changes with *message*. Returns success flag."""
    try:
        configure_user(work_dir)
        repo = Repo(work_dir)
        repo.index.commit(message)
        logger.info("Git commit successful: %s", message)
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Git commit failed: %s", exc)
        return False


def get_remote_url(work_dir: str) -> Optional[str]:
    """Return the URL of the *origin* remote, or ``None`` if unavailable."""
    try:
        repo = Repo(work_dir)
        return repo.remotes.origin.url
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def parse_github_owner_repo(remote_url: str) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(owner, repo)`` from a GitHub remote URL.

    Supports both HTTPS and SSH URL formats.
    Returns ``(None, None)`` when the URL does not match.
    """
    match = re.search(r"github\.com[:/](.+)/(.+?)(\.git)?$", remote_url)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def push(work_dir: str, token: str) -> tuple[bool, str]:
    """Push the current branch to *origin*, injecting *token* into the remote URL if needed.

    Returns ``(success, message)``.
    """
    if not token:
        logger.error("GITHUB_TOKEN missing for git push")
        return False, "ERROR: GITHUB_TOKEN missing"

    try:
        current_branch_name = get_current_branch(work_dir)
        if not current_branch_name:
            logger.error("Could not determine current branch")
            return False, "ERROR: Could not determine current branch"

        if current_branch_name in ("main", "master"):
            logger.warning("Attempted to push to default branch '%s'", current_branch_name)
            return False, f"ERROR: Cannot push to default branch '{current_branch_name}'"

        repo = Repo(work_dir)
        current_url = repo.remotes.origin.url

        if "https://" in current_url and "@" not in current_url:
            auth_url = current_url.replace("https://", f"https://{token}@")
            repo.remotes.origin.set_url(auth_url)

        repo.git.push("-u", "origin", "HEAD")
        logger.info("Git push successful")
        return True, "Push successful"
    except GitCommandError as exc:
        safe_msg = str(exc).replace(token, "***") if token else str(exc)
        logger.error("Git push failed: %s", safe_msg)
        return False, f"Push FAILED: {safe_msg}"
