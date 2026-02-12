"""A collection of tools for the agent to interact with files"""

import logging
import os

from langchain_core.tools import tool

from app.agent.utils import get_workspace

logger = logging.getLogger(__name__)


def _get_full_path(filepath: str) -> str:
    """Remove leading slashes to prevent absolute paths."""
    # FIX: Remove leading slashes
    clean_path = filepath.lstrip("/")
    full_path = os.path.join(get_workspace(), clean_path)

    full_path_real = os.path.realpath(full_path)
    workspace_real = os.path.realpath(get_workspace())
    if not full_path_real.startswith(workspace_real):
        return f"Access denied target file: {full_path_real} is not in workspace {workspace_real}"
    return full_path


def write_to_file_in_workspace(filepath: str, content: str):
    """
    Writes content to a file.
    """
    try:
        full_path = _get_full_path(filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {full_path}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"ERROR writing file: {str(e)}"


def read_file_in_workspace(filepath: str):
    """
    Reads the content of a file.
    """
    try:
        full_path = _get_full_path(filepath)
        if not os.path.exists(full_path):
            return (
                f"ERROR: File {full_path} does not exist. "
                + "(Current dir: {os.listdir(WORKSPACE)})"
            )

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content:
                return "(File is empty)"
            return content
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"ERROR reading file: {str(e)}"


@tool
def read_file(filepath: str):
    """
    Reads the content of a file.
    """
    return read_file_in_workspace(filepath)


@tool
def list_files(directory: str = "."):
    """
    Lists files in a directory (recursive).
    """
    try:
        clean_dir = directory.lstrip("/")
        target_dir = os.path.join(get_workspace(), clean_dir)
        target_dir_real = os.path.realpath(target_dir)
        workspace_real = os.path.realpath(get_workspace())
        if not target_dir_real.startswith(workspace_real):
            logger.warning(
                "Access denied target directory: %s is not in workspace %s",
                target_dir_real,
                workspace_real,
            )
            return "Access denied"

        file_list = []
        for root, _, files in os.walk(target_dir):
            if ".git" in root:
                continue
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), get_workspace())
                file_list.append(rel_path)
        return "\n".join(file_list) if file_list else "No files found."
    except Exception as e:  # pylint: disable=broad-exception-caught
        return str(e)


@tool
def write_to_file(filepath: str, content: str):
    """
    Writes content to a file.
    """
    return write_to_file_in_workspace(filepath, content)
