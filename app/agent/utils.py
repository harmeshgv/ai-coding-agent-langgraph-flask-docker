"""Environment helpers for locating the workspace and workbench."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime
from typing import Final, Optional

from app.core.config import get_env_settings

__all__ = [
    "get_workbench",
    "get_workspace",
    "get_codespace",
    "save_state_to_workspace",
    "get_current_git_branch",
]


DEFAULT_WORKSPACE: Final[str] = "/coding-agent-workspace"


def get_workspace() -> str:
    """Return the workspace directory path."""
    return get_env_settings().workspace


def get_workbench() -> str:
    """Return the workbench container name."""
    return get_env_settings().workbench


def get_codespace() -> str:
    """Return the path to the code repository."""
    return f"{get_workspace()}/code"


def save_state_to_workspace(state: dict, filename: str = "agent_state.json") -> str:
    """Saves the agent state to a JSON file in the workspace.

    This function serializes the agent's state, handling complex objects
    like BaseMessage and enums, and writes it to a specified file.

    Args:
        state: The AgentState dictionary to save.
        filename: The name of the file to save the state to.

    Returns:
        The full path to the saved file.
    """
    workspace_path = get_workspace()
    file_path = os.path.join(workspace_path, filename)

    # Ensure the workspace directory exists
    os.makedirs(workspace_path, exist_ok=True)

    # Create a serializable copy of the state to avoid modifying the original
    serializable_state = dict(state)

    # Convert BaseMessage objects to a serializable format
    if "messages" in serializable_state and serializable_state["messages"]:
        serializable_state["messages"] = [
            {"type": msg.type, "content": str(msg.content)}
            for msg in serializable_state["messages"]
        ]

    serializable_state["task"] = asdict(serializable_state["task"])
    serializable_state["last_update"] = datetime.now().astimezone().isoformat()
    temp_path = file_path + ".tmp"

    # 1. In temporäre Datei schreiben
    with open(temp_path, "w", encoding="utf-8") as f:
        # default=str hilft bei Objekten, die nicht JSON serializable sind (wie datetime)
        json.dump(serializable_state, f, indent=2, default=str)

    # 2. Atomares Verschieben (Das ist im OS eine einzige Operation)
    shutil.move(temp_path, file_path)
    return file_path


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
