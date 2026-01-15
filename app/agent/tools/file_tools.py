"""A collection of tools for the agent to interact with files"""

import logging
import os

from langchain_core.tools import tool

from agent.utils import get_workspace

logger = logging.getLogger(__name__)


@tool
def read_file(filepath: str):
    """
    Reads the content of a file.
    """
    try:
        # FIX: Führende Slashes entfernen, um absolute Pfade zu verhindern
        clean_path = filepath.lstrip("/")
        full_path = os.path.join(get_workspace(), clean_path)

        # Security
        if not os.path.abspath(full_path).startswith(get_workspace()):
            return "ERROR: Access denied."

        if not os.path.exists(full_path):
            return (
                f"ERROR: File {clean_path} does not exist. "
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
def list_files(directory: str = "."):
    """
    Lists files in a directory (recursive).
    """
    try:
        clean_dir = directory.lstrip("/")
        target_dir = os.path.join(get_workspace(), clean_dir)
        if not os.path.abspath(target_dir).startswith(get_workspace()):
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
    try:
        # FIX: Führende Slashes entfernen
        clean_path = filepath.lstrip("/")
        full_path = os.path.join(get_workspace(), clean_path)

        if not os.path.abspath(full_path).startswith(get_workspace()):
            return "ERROR: Access denied."

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {clean_path}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"ERROR writing file: {str(e)}"
