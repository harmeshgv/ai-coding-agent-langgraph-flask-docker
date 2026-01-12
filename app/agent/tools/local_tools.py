"""
A collection of tools for the agent to interact with the local environment,
including Docker, Git, and the file system.
"""

import logging
import os
import re
import subprocess

import docker
import requests
from core.repositories import upsert_issue
from docker.errors import APIError, NotFound
from flask import current_app
from langchain_core.tools import tool

from agent.utils import get_workbench, get_workspace

logger = logging.getLogger(__name__)


# Initialisiert die Verbindung zur "Fernbedienung" (docker.sock)
# Das funktioniert automatisch, wenn der Socket gemountet ist.
try:
    CLIENT = docker.from_env()
except Exception as e:  # pylint: disable=broad-exception-caught
    logger.warning("No docker connection! %s", e)
    CLIENT = None


@tool
def report_test_result(result: str, summary: str):
    """
    Reports the final outcome of the testing phase.
    result: 'pass' if everything is green (PR created), 'fail' if fix is needed.
    summary: Brief explanation.
    """
    return f"Test Process Completed. Result: {result}. Summary: {summary}"


MAX_TOOL_OUTPUT_CHARS = 20000


def _truncate_tool_output(output: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncates the output to stay within the prompt budget."""
    if len(output) <= limit:
        return output

    # Truncate middle to keep start and end for better context
    half = limit // 2
    return (
        output[:half]
        + "\n... [output truncated to stay within prompt budget] ...\n"
        + output[-half:]
    )


@tool
def run_java_command(command: str):
    """
    Führt einen Shell-Befehl im Java-Container aus.
    Nutze dies für: 'mvn clean install', 'mvn test', 'java -jar ...'.
    Gib NUR den Befehl als String an.
    """
    if not CLIENT:
        return "Error: Docker client not initialized. Is the socket mounted?"

    try:
        container = CLIENT.containers.get(get_workbench())

        if container.status != "running":
            return (
                f"Error: Container {get_workbench()} is not running "
                + "(Status: {container.status})."
            )

        logger.info("Executing in Java-Box: %s", command)

        exec_result = container.exec_run(command, workdir=get_workspace())

        output = exec_result.output.decode("utf-8")
        exit_code = exec_result.exit_code

        logger.debug("--- COMMAND OUTPUT (%s) ---\n%s\n---", command, output)
        output = _truncate_tool_output(output)

        return (
            f"✅ SUCCESS:\n{output}"
            if exit_code == 0
            else f"❌ FAILED (Exit Code {exit_code}):\n{output}"
        )

    except NotFound:
        return (
            f"Error: Container '{get_workbench()}' not found. "
            + "Please start the docker-compose setup."
        )
    except APIError as e:
        return f"Docker API Error: {str(e)}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"System Error: {str(e)}"


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


@tool
def git_create_branch(
    branch_name: str, card_id: str | None = None, card_name: str | None = None
):
    """
    Creates a new git branch and switches to it immediately.
    If card_id and card_name are provided, persists the card-branch relationship in the database.
    Example: 'feature/login-page' or 'fix/bug-123'.
    """
    try:
        logger.info(
            "Creating branch '%s' in workspace '%s'", branch_name, get_workspace()
        )
        # 'checkout -b' erstellt und wechselt in einem Schritt
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=get_workspace(),
            check=True,
            capture_output=True,
            text=True,
        )

        if card_id and card_name:
            try:
                with current_app.app_context():
                    remote_url = subprocess.check_output(
                        ["git", "remote", "get-url", "origin"],
                        cwd=get_workspace(),
                        text=True,
                    ).strip()
                    upsert_issue(card_id, card_name, branch_name, remote_url)
                    logger.info(
                        "Persisted Issue: card_id=%s, branch=%s", card_id, branch_name
                    )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to persist Issue relationship: %s", e)

        return f"Successfully created and switched to branch '{branch_name}'."
    except subprocess.CalledProcessError as e:
        return f"ERROR creating branch: {e.stderr}"


@tool
def git_push_origin():
    """
    Pushes the current branch to the remote repository.
    Sets the upstream automatically.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "ERROR: GITHUB_TOKEN missing."

    try:
        # Check current branch name
        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=get_workspace(), text=True
        ).strip()

        # Prevent pushing to default branches
        if current_branch in ["main", "master"]:
            logger.warning("Attempted to push to default branch '%s'", current_branch)
            return f"ERROR: Cannot push to default branch '{current_branch}'. Create a feature branch first!"

        # URL Auth Logic (wie vorher)
        current_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=get_workspace(), text=True
        ).strip()
        if "https://" in current_url and "@" not in current_url:
            auth_url = current_url.replace("https://", f"https://{token}@")
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=get_workspace(),
                check=True,
            )

        # WICHTIG: 'git push -u origin HEAD' pusht den aktuellen Branch (egal wie er heißt)
        result = subprocess.run(
            ["git", "push", "-u", "origin", "HEAD"],
            cwd=get_workspace(),
            capture_output=True,
            text=True,
            check=True,
        )
        return f"Push successful:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        safe_stderr = e.stderr.replace(token, "***") if token else e.stderr
        return f"Push FAILED:\n{safe_stderr}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"ERROR: {str(e)}"


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


@tool
def create_or_update_github_pr(title: str, body: str):  # pylint: disable=too-many-return-statements
    """
    Creates a Pull Request on GitHub for the current branch.
    If a PR already exists for this branch, adds a comment instead.
    Target is usually 'main' or 'master'.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "ERROR: GITHUB_TOKEN missing."

    try:
        # 1. Get remote URL
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=get_workspace(), text=True
        ).strip()

        match = re.search(r"github\.com[:/](.+)/(.+?)(\.git)?$", remote_url)
        if not match:
            return f"ERROR: Could not parse Owner/Repo from URL: {remote_url}"

        owner, repo = match.group(1), match.group(2)

        # 2. Get current branch name
        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=get_workspace(), text=True
        ).strip()

        if current_branch in ["main", "master"]:
            logger.warning("You are on main/master. Create a feature branch first!")
            return "ERROR: You are on main/master. Create a feature branch first!"

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # 3. Check for existing PR
        existing_pr = _find_existing_pr(owner, repo, current_branch, headers)

        # 4. If PR exists, update it
        if existing_pr:
            response = _update_existing_pr(existing_pr, owner, repo, headers, body)
            logger.info("Updated existing PR response: %s", response)
            return response

        # 5. Create new PR if none exists
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        payload = {"title": title, "body": body, "head": current_branch, "base": "main"}

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        # 6. If 'main' not found, try 'master'
        if response.status_code == 422:
            logger.info("Target 'main' not found, trying 'master'...")
            payload["base"] = "master"
            response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code == 201:
            pr_url = response.json().get("html_url")
            return f"SUCCESS: Pull Request created: {pr_url}"

        return f"ERROR creating PR: {response.status_code} - {response.text}"

    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"ERROR: {str(e)}"


@tool
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


@tool
def git_commit(message: str):
    """Commits staged changes."""
    try:
        # Git Identität muss im Container gesetzt sein, sonst meckert Git
        # (Alternativ in Dockerfile setzen)
        subprocess.run(
            ["git", "config", "user.email", "agent@bot.com"],
            cwd=get_workspace(),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Coding Agent"],
            cwd=get_workspace(),
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=get_workspace(),
            check=True,
            capture_output=True,
            text=True,
        )
        return "Commit successful."
    except subprocess.CalledProcessError as e:
        return f"Error committing: {e.stderr}"


@tool
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
