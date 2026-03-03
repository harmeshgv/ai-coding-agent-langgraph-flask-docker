"""Environment helpers for locating the workspace and workbench."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from typing import Final

from app.core.config import get_env_settings

__all__ = [
    "get_workbench",
    "get_workspace",
    "save_state_to_instance",
]


DEFAULT_WORKSPACE: Final[str] = "/coding-agent-workspace"


def get_workspace() -> str:
    """Return the workspace directory path."""
    return get_env_settings().workspace


def get_instance_dir() -> str:
    """Return the instance directory path."""
    return get_env_settings().instance_dir


def get_workbench() -> str:
    """Return the workbench container name."""
    return get_env_settings().workbench


def save_state_to_instance(state: dict, filename: str = "agent_state.json") -> str:
    """Saves the agent state to a JSON file in the instance directory.

    This function serializes the agent's state, handling complex objects
    like BaseMessage and enums, and writes it to a specified file.

    Args:
        state: The AgentState dictionary to save.
        filename: The name of the file to save the state to.

    Returns:
        The full path to the saved file.
    """
    instance_path = get_instance_dir()
    file_path = os.path.join(instance_path, filename)

    # Ensure the instance directory exists
    os.makedirs(instance_path, exist_ok=True)

    # Create a serializable copy of the state to avoid modifying the original
    serializable_state = dict(state)

    # Convert BaseMessage objects to a serializable format
    if "messages" in serializable_state and serializable_state["messages"]:
        serializable_state["messages"] = [
            {"type": msg.type, "content": str(msg.content)}
            for msg in serializable_state["messages"]
        ]

    serializable_state["provider_task"] = asdict(serializable_state["provider_task"])
    serializable_state["agent_task"] = serializable_state["agent_task"].to_dict()
    serializable_state["last_update"] = datetime.now().astimezone().isoformat()
    temp_path = file_path + ".tmp"

    # 1. In temporäre Datei schreiben
    with open(temp_path, "w", encoding="utf-8") as f:
        # default=str hilft bei Objekten, die nicht JSON serializable sind (wie datetime)
        json.dump(serializable_state, f, indent=2, default=str)

    # 2. Atomares Verschieben (Das ist im OS eine einzige Operation)
    shutil.move(temp_path, file_path)
    return file_path
