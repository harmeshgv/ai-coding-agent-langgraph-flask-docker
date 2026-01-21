"""Environment helpers for locating the workspace and workbench."""

from __future__ import annotations

import os
import subprocess
from typing import Final, Optional

__all__ = [
    "get_workbench",
    "get_workspace",
    "get_codespace",
    "get_current_git_branch",
]


DEFAULT_WORKSPACE: Final[str] = "/coding-agent-workspace"


def get_workspace() -> str:
    """Return the configured workspace path or a sensible default."""
    return os.environ.get("WORKSPACE", DEFAULT_WORKSPACE)


def get_workbench() -> str:
    """Return the active workbench identifier (e.g., 'workbench-backend')."""
    return os.environ.get("WORKBENCH", "")


def get_codespace() -> str:
    """Return the path to the code repository."""
    return f"{get_workspace()}/code"


def get_current_git_branch() -> Optional[str]:
    """
    Get the current git branch name.

    Returns:
        Current branch name or None if unable to determine
    """
    try:
        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=get_codespace(),
            text=True,
        ).strip()
        return current_branch
    except subprocess.CalledProcessError:
        return None
