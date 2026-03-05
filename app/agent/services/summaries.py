"""Utility helpers for tracking agent summaries and finish_task metadata."""

from typing import Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage

from app.agent.state import AgentState, AgentSummary


def _create_agent_summary(role: str, summary: str) -> Optional[AgentSummary]:
    """Create an AgentSummary instance for a specific role."""
    if summary is None:
        return None

    clean_summary = summary.strip()
    if not clean_summary:
        return None

    return AgentSummary(role=role, summary=clean_summary)


def append_agent_summary(
    summary_entries: list[AgentSummary],
    role: str,
    summary: str,
) -> list[AgentSummary]:
    """Append a normalized summary entry for the given role to the provided list."""
    entry = _create_agent_summary(role, summary)
    if not entry:
        return summary_entries

    summary_entries.append(entry)
    return summary_entries


def record_finish_task_summary(
    state: AgentState,
    role: str,
    ai_message: BaseMessage,
) -> Tuple[bool, list[AgentSummary]]:
    """
    Store any finish_task summaries emitted by the given role.

    Args:
        state: The current agent state.
        role: The role that emitted the summary.
        ai_message: The AIMessage response from the LLM.

    Returns:
        A tuple containing a boolean indicating whether a summary was recorded
        and the updated summary entries.
    """
    summary_entries = list[AgentSummary](state.get("agent_summary") or [])
    if not isinstance(ai_message, AIMessage) or not getattr(ai_message, "tool_calls", None):
        return False, summary_entries

    recorded = False
    for tool_call in ai_message.tool_calls:
        if tool_call.get("name") != "finish_task":
            continue

        args = tool_call.get("args") or {}
        summary = args.get("summary", "")
        summary_entries = append_agent_summary(summary_entries, role, summary)
        args["agent_role"] = role
        tool_call["args"] = args
        recorded = True

    state["agent_summary"] = summary_entries
    return recorded, summary_entries


def has_finish_task_call(message: BaseMessage) -> bool:
    """Check whether the given message includes a finish_task tool call."""
    if not isinstance(message, AIMessage):
        return False

    # Only check valid parsed tool_calls (invalid_tool_calls can't be executed)
    tool_calls = message.tool_calls or []

    if not tool_calls:
        return False

    return any(tool_call.get("name") == "finish_task" for tool_call in tool_calls)


def collect_finish_task_summaries(
    message: BaseMessage,
) -> list[tuple[Optional[str], str]]:
    """Extract the summary strings from finish_task tool calls within a message."""
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


def build_agent_summary_text(state: AgentState, separator: str = "\n\n") -> Optional[str]:
    """Join all recorded summary entries into a single string."""
    entries = get_agent_summary_entries(state)
    if not entries:
        return None
    return separator.join(entry.to_markdown() for entry in entries)


def build_agent_summary_markdown(
    state: AgentState,
    heading: Optional[str] = None,
    bullet_prefix: str = "- ",
    line_separator: str = "\n",
) -> Optional[str]:
    """Build a Markdown-friendly block with bulleted summary entries."""
    entries = get_agent_summary_entries(state)
    if not entries:
        return None

    bullet_lines = [f"{bullet_prefix}{entry.to_markdown()}" for entry in entries]
    body = line_separator.join(bullet_lines)

    if heading:
        normalized_heading = heading.strip()
        if normalized_heading:
            return f"{normalized_heading}\n\n{body}"

    return body


def get_agent_summary_entries(state: AgentState) -> list[AgentSummary]:
    """Return the list of cached summary entries."""
    cached_entries = [
        entry for entry in (state.get("agent_summary") or []) if isinstance(entry, AgentSummary)
    ]
    return _deduplicate_consecutive(cached_entries)



def _deduplicate_consecutive(entries: list[AgentSummary]) -> list[AgentSummary]:
    """Remove consecutive duplicate entries while preserving order."""
    deduplicated: list[AgentSummary] = []
    previous: AgentSummary | None = None
    for entry in entries:
        if previous is None or entry.role != previous.role or entry.summary != previous.summary:
            deduplicated.append(entry)
        previous = entry
    return deduplicated
