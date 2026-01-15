"""
A collection of tools for the agent to interact with the local environment,
including Docker, Git, and the file system.
"""

import logging
import os
import subprocess

import requests
from langchain_core.tools import tool

from agent.utils import get_workspace

logger = logging.getLogger(__name__)


@tool
def report_test_result(result: str, summary: str):
    """
    Reports the final outcome of the testing phase.
    result: 'pass' if everything is green (PR created), 'fail' if fix is needed.
    summary: Brief explanation.
    """
    return f"Test Process Completed. Result: {result}. Summary: {summary}"


# --- GIT & FILE TOOLS ---
@tool
def log_thought(thought: str):
    """
    Logs a thought or observation.
    Use this tool to 'think out loud' or plan your next step without breaking the workflow.
    """
    # Wir loggen es nur, damit wir es sehen. Für den Agenten ist es ein erfolgreicher Schritt.
    logger.debug("🤔 AGENT THOUGHT: %s", thought)
    return "Thought recorded. Proceed with the next tool."


@tool
def finish_task(summary: str):  # pylint: disable=unused-argument
    """
    Call this tool when you have completed the task.
    Provide a detailed summary of the changes you made.
    """
    return "Task marked as finished."


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


def _find_existing_pr(owner: str, repo: str, branch: str, headers: dict) -> dict | None:
    """
    Helper to find an existing open PR for the given branch.
    Returns PR data dict if found, None otherwise.
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        params = {"head": f"{owner}:{branch}", "state": "open"}
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            pulls = response.json()
            if pulls:
                return pulls[0]
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to check for existing PR: %s", e)
        return None


def _update_existing_pr(existing_pr, owner: str, repo: str, headers: dict, body: str):
    pr_number = existing_pr.get("number")
    pr_url = existing_pr.get("html_url")

    comment_url = (
        f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    )
    comment_payload = {"body": f"**Automated Update:**\n\n{body}"}

    comment_response = requests.post(
        comment_url, json=comment_payload, headers=headers, timeout=10
    )

    if comment_response.status_code == 201:
        return f"SUCCESS: Added comment to existing PR: {pr_url}"

    return (
        "ERROR adding comment to PR: "
        + f"{comment_response.status_code} - {comment_response.text}"
    )


def git_add(files: list):  # repo_path ignorieren wir oft besser zugunsten der ENV
    """Adds files to staging area."""
    try:
        subprocess.run(
            ["git", "add"] + files,
            cwd=get_workspace(),
            check=True,
            capture_output=True,
            text=True,
        )
        return f"Successfully added {files}"
    except subprocess.CalledProcessError as e:
        return f"Error adding files: {e.stderr}"


def git_status():
    """Checks git status."""
    try:
        result = subprocess.run(
            ["git", "status"],
            cwd=get_workspace(),
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("git status: %s", result.stdout)
        return result.stdout
    except Exception as e:  # pylint: disable=broad-exception-caught
        return str(e)
