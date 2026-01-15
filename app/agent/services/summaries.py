"""Utility helpers for tracking agent summaries and finish_task metadata."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from langchain_core.messages import AIMessage, BaseMessage

from agent.state import AgentState

__all__ = [
    "append_agent_summary",
    "build_agent_summary_markdown",
    "build_agent_summary_text",
    "collect_finish_task_summaries",
    "get_agent_summary_entries",
    "has_finish_task_call",
    "record_finish_task_summary",
]


def _format_agent_summary_entry(role: str, summary: str) -> Optional[str]:
    """Build a normalized summary entry for a specific role."""
    if summary is None:
        return None

    clean_summary = summary.strip()
    if not clean_summary:
        return None

    role_prefix = role.capitalize()
    return f"**[{role_prefix}]** {clean_summary}"


def append_agent_summary(
    summary_entries: list[str],
    role: str,
    summary: str,
) -> list[str]:
    """Append a normalized summary entry for the given role to the provided list."""
    entry = _format_agent_summary_entry(role, summary)
    if not entry:
        return summary_entries

    summary_entries.append(entry)
    return summary_entries


def record_finish_task_summary(
    state: AgentState,
    role: str,
    ai_message: BaseMessage,
) -> Tuple[bool, list[str]]:
    """Store any finish_task summaries emitted by the given role."""
    summary_entries = list(state.get("agent_summary") or [])
    if not isinstance(ai_message, AIMessage) or not getattr(
        ai_message, "tool_calls", None
    ):
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
    if not isinstance(message, AIMessage) or not getattr(message, "tool_calls", None):
        return False

    return any(
        tool_call.get("name") == "finish_task" for tool_call in message.tool_calls
    )


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


def build_agent_summary_text(
    state: AgentState, separator: str = "\n\n"
) -> Optional[str]:
    """Join all recorded summary entries into a single string."""
    entries = get_agent_summary_entries(state)
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
    """Build a Markdown-friendly block with bulleted summary entries."""
    entries = get_agent_summary_entries(state)
    if not entries:
        return None

    bullet_lines = [f"{bullet_prefix}{entry}" for entry in entries]
    body = line_separator.join(bullet_lines)

    if heading:
        normalized_heading = heading.strip()
        if normalized_heading:
            return f"{normalized_heading}\n\n{body}"

    return body


def get_agent_summary_entries(state: AgentState) -> list[str]:
    """Return the list of cached summary entries, with message-based fallback."""
    cached_entries = [
        entry for entry in (state.get("agent_summary") or []) if isinstance(entry, str)
    ]
    if cached_entries:
        return cached_entries

    return _derive_summaries_from_messages(state.get("messages") or [])


def _derive_summaries_from_messages(messages: Sequence[BaseMessage]) -> list[str]:
    """Build summary entries by scanning the message history for finish_task calls."""
    derived: list[str] = []
    for message in messages:
        summaries = collect_finish_task_summaries(message)
        for role, summary in summaries:
            entry = _format_agent_summary_entry(role or "agent", summary)
            if entry:
                derived.append(entry)
    return derived
