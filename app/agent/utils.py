"""Environment helpers for locating the workspace and workbench."""

from __future__ import annotations

import os
from typing import Final

__all__ = [
    "get_workbench",
    "get_workspace",
]


DEFAULT_WORKSPACE: Final[str] = "/coding-agent-workspace"


def get_workspace() -> str:
    """Return the configured workspace path or a sensible default."""
    return os.environ.get("WORKSPACE", DEFAULT_WORKSPACE)


def get_workbench() -> str:
    """Return the active workbench identifier (e.g., 'workbench-backend')."""
    return os.environ.get("WORKBENCH", "")
