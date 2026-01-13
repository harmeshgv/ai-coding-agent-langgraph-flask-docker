"""
Utility functions for the AI Coding Agent.
"""

import logging
import os
import re
import shutil
from typing import Any, Optional, Sequence
from urllib.parse import urlparse, urlunparse
from git import Repo
from git.exc import GitCommandError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agent.state import AgentState

logger = logging.getLogger(__name__)


def _format_agent_summary_entry(role: str, summary: str) -> Optional[str]:
    """
    Build a normalized summary entry for a specific role.
    """
    if summary is None:
        return None

    clean_summary = summary.strip()
    if not clean_summary:
        return None

    role_prefix = role.capitalize()
    return f"**[{role_prefix}]** {clean_summary}"


def append_agent_summary(state: AgentState, role: str, summary: str) -> None:
    """
    Append a normalized summary entry for the given role to the AgentState.
    """
    entry = _format_agent_summary_entry(role, summary)
    if not entry:
        return

    existing = list(state.get("agent_summary") or [])
    existing.append(entry)
    state["agent_summary"] = existing


def record_finish_task_summary(
    state: AgentState,
    role: str,
    ai_message: BaseMessage,
) -> bool:
    """
    Store any finish_task summaries emitted by the given role.
    """
    if not isinstance(ai_message, AIMessage) or not getattr(ai_message, "tool_calls", None):
        return False

    recorded = False
    for tool_call in ai_message.tool_calls:
        if tool_call.get("name") != "finish_task":
            continue

        args = tool_call.get("args") or {}
        summary = args.get("summary", "")
        # Persist the normalized summary so downstream nodes can reuse the cached list
        append_agent_summary(state, role, summary)
        # Also stash the role on the tool call to allow reconstruction when the cache is absent
        args["agent_role"] = role
        tool_call["args"] = args
        recorded = True

    return recorded


def has_finish_task_call(message: BaseMessage) -> bool:
    """
    Check whether the given message includes a finish_task tool call.
    """
    if not isinstance(message, AIMessage) or not getattr(message, "tool_calls", None):
        return False

    return any(tool_call.get("name") == "finish_task" for tool_call in message.tool_calls)


def collect_finish_task_summaries(message: BaseMessage) -> list[tuple[Optional[str], str]]:
    """
    Extract the summary strings from any finish_task tool calls within a message.
    """
    summaries: list[tuple[Optional[str], str]] = []
    if not isinstance(message, AIMessage) or not getattr(message, "tool_calls", None):
        return summaries

    for tool_call in message.tool_calls:
        if tool_call.get("name") != "finish_task":
            continue

        args = tool_call.get("args") or {}
        summary = args.get("summary")
        if summary:
            role = args.get("agent_role")
            summaries.append((role, str(summary)))

    return summaries


def build_agent_summary_text(
    state: AgentState,
    separator: str = "\n\n",
) -> Optional[str]:
    """
    Join all recorded summary entries into a single string.
    """
    entries = _get_normalized_agent_summary_entries(state)
    if not entries:
        return None
    return separator.join(entries)


def build_agent_summary_markdown(
    state: AgentState,
    *,
    heading: Optional[str] = None,
    bullet_prefix: str = "- ",
    line_separator: str = "\n",
) -> Optional[str]:
    """
    Build a Markdown-friendly block with bulleted summary entries.
    """
    entries = _get_normalized_agent_summary_entries(state)
    if not entries:
        return None

    bullet_lines = [f"{bullet_prefix}{entry}" for entry in entries]
    body = line_separator.join(bullet_lines)

    if heading:
        normalized_heading = heading.strip()
        if normalized_heading:
            return f"{normalized_heading}\n\n{body}"

    return body


def _get_normalized_agent_summary_entries(state: AgentState) -> list[str]:
    """
    Return the list of cached summary entries, falling back to scanning messages.
    """
    cached_entries = [
        entry for entry in (state.get("agent_summary") or []) if isinstance(entry, str)
    ]
    if cached_entries:
        return cached_entries

    derived_entries = _derive_summaries_from_messages(state.get("messages") or [])
    return derived_entries


def _derive_summaries_from_messages(messages: Sequence[BaseMessage]) -> list[str]:
    """
    Build summary entries by scanning the message history for finish_task calls.
    """
    derived: list[str] = []
    for message in messages:
        summaries = collect_finish_task_summaries(message)
        for role, summary in summaries:
            entry = _format_agent_summary_entry(role or "agent", summary)
            if entry:
                derived.append(entry)
    return derived


def safe_truncate(value: Any, length: int = 100) -> str:
    """
    Converts any value to string, truncates it to the desired length,
    and replaces newlines for cleaner log output.
    """
    string_value = str(value)
    if len(string_value) > length:
        return string_value[:length] + "..."
    return string_value.replace("\n", "\\n")


def log_agent_response(
    agent_name: str,
    response: AIMessage,
    *,
    attempt: Optional[int] = None,
    content_limit: int = 150,
    arg_limit: int = 250,
) -> None:
    """
    Logs LLM responses consistently across nodes, including tool calls and content.
    """
    header = f"\n=== {agent_name.upper()} RESPONSE"
    if attempt is not None:
        header += f" (Attempt {attempt})"
    header += " ==="
    logger.info(header)

    tool_calls = getattr(response, "tool_calls", []) or []
    if tool_calls:
        for tool_call in tool_calls:
            name = tool_call.get("name", "unknown")
            logger.info("Tool Call: %s", name)
            args = tool_call.get("args", {}) or {}
            for key, value in args.items():
                logger.info(" └─ %s: %s", key, safe_truncate(value, length=arg_limit))

    if getattr(response, "content", None):
        logger.info("Content: %s", safe_truncate(response.content, content_limit))


def _log_message_detail(
    idx,
    message,
    content_limit: int,
):
    logger.info(
        "[%02d] %s",
        idx,
        getattr(message, "type", message.__class__.__name__).upper(),
    )
    content = getattr(message, "content", None)
    if content is not None:
        logger.info("     content      : %s", safe_truncate(content, content_limit))

    name = getattr(message, "name", None)
    if name:
        logger.info("     name         : %s", name)

    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        logger.info("     tool_call_id : %s", tool_call_id)


def _log_additional_kwargs(
    message,
    arg_limit: int,
):
    additional_kwargs = getattr(message, "additional_kwargs", {})
    if additional_kwargs:
        logger.info("     additional_kwargs:")
        for key, value in additional_kwargs.items():
            logger.info("         %s: %s", key, safe_truncate(value, arg_limit))


def _log_tool_calls(
    message,
    arg_limit: int,
):
    tool_calls = getattr(message, "tool_calls", [])
    if tool_calls:
        logger.info("     tool_calls:")
        for tool_idx, tool_call in enumerate(tool_calls, start=1):
            tool_name = tool_call.get("name", "unknown")
            logger.info("         (%d) %s", tool_idx, tool_name)
            args = tool_call.get("args", {})
            for key, value in args.items():
                logger.info("             %s: %s", key, safe_truncate(value, arg_limit))


def log_agent_state(
    state: dict,
    content_limit: int = 100,
    arg_limit: int = 250,
) -> None:
    """
    Logs a snapshot of the AgentState, including a detailed message dump.
    """
    logger.info("\n=== AGENT STATE SNAPSHOT ===")
    logger.info("next_step         : %s", state.get("next_step"))
    logger.info("agent_stack       : %s", state.get("agent_stack"))
    logger.info("retry_count       : %s", state.get("retry_count"))
    logger.info("test_result       : %s", state.get("test_result"))
    logger.info("error_log         : %s", state.get("error_log"))
    logger.info("trello_card_id    : %s", state.get("trello_card_id"))
    logger.info("trello_list_id    : %s", state.get("trello_list_id"))

    messages = state.get("messages", [])
    logger.info("\n--- Messages (%d) ---", len(messages))
    for idx, message in enumerate(messages, start=1):
        _log_message_detail(idx, message, content_limit)
        _log_additional_kwargs(message, arg_limit)
        _log_tool_calls(message, arg_limit)

    logger.info("=== END OF STATE SNAPSHOT ===")


# Hilfsfunktion, um Redundanz zu vermeiden
def get_workspace():
    """Get the workspace path from the environment variable."""
    return os.environ.get("WORKSPACE", "/coding-agent-workspace")


def get_workbench():
    """Get the workbench path from the environment variable."""
    return os.environ.get("WORKBENCH", "")


def load_system_prompt(stack: str, role: str) -> str:
    """
    Lädt den System-Prompt basierend auf Stack und Rolle.
    z.B. stack="backend", role="coder" -> liest workbench/backend/systemprompt_coder.md
    """

    file_path = os.path.join("workbench", stack, f"systemprompt_{role}.md")

    logger.info("Loading system prompt: %s", file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback, falls Datei fehlt (wichtig für Robustheit!)
        logger.warning("WARNUNG: System Prompt not found: %s", file_path)
        return "You are a helpful coding assistent."


def _estimate_tokens(messages: list[BaseMessage]) -> int:
    """Rough estimate of token count for messages (avg ~4 chars per token)."""
    total_chars = 0
    for msg in messages:
        if hasattr(msg, "content") and msg.content:
            total_chars += len(str(msg.content))

        if isinstance(msg, AIMessage):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = getattr(msg, "tool_calls", []) or []
                total_chars += len(str(tool_calls))
    return total_chars // 4


def _find_first_human_message(messages: list[BaseMessage]) -> int | None:
    """Find index of first HumanMessage (original task)."""
    # Scan through messages to locate the first HumanMessage
    # This represents the original user task/request
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            return idx
    return None


def _find_safe_start_boundary(
    messages: list[BaseMessage], recent_start_idx: int
) -> int:
    """
    Find a safe starting point by scanning forward from the cutoff.
    Safe boundaries are: HumanMessage or AIMessage
    """
    adjusted_start_idx = recent_start_idx

    # Scan forward from the naive cutoff point to find a valid conversation boundary
    for idx in range(recent_start_idx, len(messages)):
        msg = messages[idx]

        # HumanMessages are always safe starting points (no dependent tool responses)
        if isinstance(msg, (HumanMessage, AIMessage)):
            adjusted_start_idx = idx
            break

    return adjusted_start_idx


def _trim_trailing_invalid_ai_messages(
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """
    Remove trailing AIMessages without tool_calls.
    Mistral API requires last message to be User, Tool, or Assistant with tool_calls.
    """
    # Remove any trailing AI messages that don't have tool calls
    # Mistral API enforces: last message must be user/tool/assistant-with-tool-calls
    while messages and isinstance(messages[-1], AIMessage):
        ai_msg = messages[-1]
        # If this AI message has tool calls, it's valid as the last message
        if getattr(ai_msg, "tool_calls", None):
            break
        # Otherwise, remove it and check the previous message
        messages = messages[:-1]
    return messages


def _log_token_savings(
    original_count: int, original_tokens: int, filtered_count: int, filtered_tokens: int
) -> None:
    """Log token savings statistics."""
    # Calculate absolute and percentage token savings
    saved_tokens = original_tokens - filtered_tokens
    saved_percentage = (
        (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
    )

    # Log the filtering results for monitoring token optimization
    logger.info(
        "Message filter: %d → %d messages (~%d → ~%d tokens, saved ~%d tokens / %.1f%%)",
        original_count,
        filtered_count,
        original_tokens,
        filtered_tokens,
        saved_tokens,
        saved_percentage,
    )


def filter_messages_for_llm(
    messages: list[BaseMessage], max_messages: int = 10
) -> list[BaseMessage]:
    """
    Filters messages to keep only the most recent and relevant ones for LLM context.
    This reduces token usage by limiting the message history.

    Strategy:
    - Always keep the first HumanMessage (original task)
    - Keep the most recent complete conversation turns
    - Never break AI→Tool message pairs to maintain valid message order
    - Prevent orphaned ToolMessages that would violate API constraints

    :param messages: List of messages from state
    :param max_messages: Maximum number of messages to keep (excluding first task message)
    :return: Filtered list of messages
    """
    # Early exit for empty list
    if not messages:
        return []

    # Track original metrics for logging
    original_count = len(messages)
    original_tokens = _estimate_tokens(messages)

    # Skip filtering if message count is already within limits
    if len(messages) <= max_messages + 1:
        logger.debug(
            "Message filter: %s messages, ~%s tokens (no filtering needed)",
            original_count,
            original_tokens,
        )
        return messages

    # Step 1: Find the original user task (first HumanMessage)
    first_human_idx = _find_first_human_message(messages)

    # Step 2: Calculate naive cutoff and find safe conversation boundary
    recent_start_idx = max(0, len(messages) - max_messages)
    adjusted_start_idx = _find_safe_start_boundary(messages, recent_start_idx)

    # Step 3: Extract recent messages and trim invalid trailing AI messages
    recent_messages = messages[adjusted_start_idx:]
    recent_messages = _trim_trailing_invalid_ai_messages(recent_messages)

    # Step 4: Fallback if everything was filtered out
    if not recent_messages and messages:
        # Try to return at least the last HumanMessage
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return [msg]
        # Ultimate fallback: return last message
        return [messages[-1]] if messages else []

    # Step 5: Prepend original task if it was filtered out
    if first_human_idx is not None and first_human_idx < adjusted_start_idx:
        first_task = [messages[first_human_idx]]
        filtered_messages = first_task + recent_messages
    else:
        filtered_messages = recent_messages

    # Step 6: Log token savings
    filtered_count = len(filtered_messages)
    filtered_tokens = _estimate_tokens(filtered_messages)
    _log_token_savings(original_count, original_tokens, filtered_count, filtered_tokens)

    return filtered_messages


def sanitize_response(response: AIMessage) -> AIMessage:
    """
    Entfernt halluzinierte Tool-Calls (z.B. wenn der Name ein ganzer Satz ist).
    Verhindert API Fehler 3280 (Invalid function name).
    """
    # Wenn keine Tool Calls da sind oder es keine AI Message ist, einfach zurückgeben
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return response

    valid_tools = []
    # Erlaubte Zeichen für Funktionsnamen: a-z, A-Z, 0-9, _, -
    name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

    for tc in response.tool_calls:
        name = tc.get("name", "")
        # Check: Ist der Name im gültigen Format und nicht zu lang?
        if name_pattern.match(name) and len(name) < 64:
            valid_tools.append(tc)
        else:
            logger.warning("SANITIZER: Removed invalid tool call with name: '%s'", name)

    # Das manipulierte Objekt zurückgeben
    response.tool_calls = valid_tools
    return response


def save_graph_as_png(graph):
    """Save the graph as a PNG file."""
    png_bytes = graph.get_graph().draw_mermaid_png()

    with open("workflow_graph.png", "wb") as f:
        f.write(png_bytes)

    print("Graph wurde als 'workflow_graph.png' gespeichert.")


def save_graph_as_mermaid(graph):
    """Save the graph as a Mermaid file."""
    mermaid_code = graph.get_graph().draw_mermaid()

    with open("workflow_graph.mmd", "w", encoding="utf-8") as f:
        f.write(mermaid_code)

    print("Graph wurde als 'workflow_graph.mmd' gespeichert.")


def normalize_git_url(url):
    """
    Normalize a Git URL by removing credentials (username/password/token).
    This allows comparing repository URLs without being affected by authentication differences.
    """
    try:
        parsed = urlparse(url)
        normalized = parsed._replace(
            netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else "")
        )
        return urlunparse(normalized)
    except Exception:  # pylint: disable=broad-exception-caught
        return url.split("@")[-1] if "@" in url else url


def ensure_repository_exists(repo_url, work_dir):
    """
    Ensure that work_dir contains the repository from repo_url.
    - Re-clone when a different repository is detected.
    - Otherwise, commit local changes, fetch origin, and leave a clean checkout.
    """

    def clean_and_clone():
        for filename in os.listdir(work_dir):
            file_path = os.path.join(work_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to delete %s. Reason: %s", file_path, e)
        logger.info("Cloning repository %s into %s", repo_url, work_dir)
        Repo.clone_from(repo_url, work_dir)

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
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Could not checkout default branch: %s, staying on current branch", e
            )

        logger.info("Repository is ready with clean checkout")

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error managing repository in %s: %s, re-cloning...", work_dir, e)
        clean_and_clone()


def checkout_branch(repo_url: str, branch_name: str, work_dir: str) -> None:
    """
    Ensure the requested branch is checked out in work_dir.
    If the branch does not exist locally, attempt to fetch it from origin.
    """
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
