"""Helpers for filtering and sanitizing agent message histories."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

__all__ = ["filter_messages_for_llm", "sanitize_response"]


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


def _collect_tool_call_ids(ai_msg: AIMessage) -> set[str]:
    """Extract all tool call IDs from an AIMessage."""
    if not ai_msg.tool_calls:
        return set()
    return {tc.get("id") for tc in ai_msg.tool_calls if tc.get("id")}


def _trim_trailing_invalid_ai(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Remove trailing AIMessages that have no content and no tool_calls.
    
    An AIMessage is invalid as the last message if it has no content AND no tool_calls.
    """
    result = list(messages)
    while result and isinstance(result[-1], AIMessage):
        ai_msg = result[-1]
        has_content = bool(getattr(ai_msg, "content", None))
        has_tool_calls = bool(getattr(ai_msg, "tool_calls", None))
        if has_content or has_tool_calls:
            break
        result = result[:-1]
    return result


def _build_window(messages: list[BaseMessage], max_messages: int) -> list[BaseMessage]:
    """Capture the most recent messages while preserving tool-call context."""
    if max_messages <= 0 or not messages:
        return []

    window_start = max(0, len(messages) - max_messages)
    window_messages = messages[window_start:]

    extended_start = window_start
    if window_messages and isinstance(window_messages[0], ToolMessage):
        target_tool_id = window_messages[0].tool_call_id
        for i in range(window_start - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_ids = _collect_tool_call_ids(msg)
                if target_tool_id in tool_ids:
                    extended_start = i
                    break

    if extended_start < window_start:
        window_messages = messages[extended_start:]

    return window_messages


# pylint: disable=too-many-locals
def filter_messages_for_llm(
    messages: list[BaseMessage], max_messages: int = 10
) -> list[BaseMessage]:
    """Filter messages to keep task context and recent history while maintaining valid stack.

    This function performs filtering that preserves message stack validity:
    1. The very first SystemMessage (if present) is always kept at the start while
       other SystemMessages remain in the timeline and are handled by the windowing logic
    2. Most recent messages up to max_messages are retained after the optional system prefix
    4. Tool call/response pairs are preserved (if AIMessage with tool_calls is kept,
       all corresponding ToolMessages are also kept)
    5. Trailing empty AIMessages are removed
    """
    if not messages:
        return []

    # Track original message count and token estimate for logging
    original_count = len(messages)
    original_tokens = _estimate_tokens(messages)

    # Keep only the very first SystemMessage (if it starts the stack)
    first_system_message = messages[0] if isinstance(messages[0], SystemMessage) else None
    remaining_messages = messages[1:] if first_system_message else messages

    if not remaining_messages:
        return [first_system_message] if first_system_message else []

    # Apply sliding window across remaining messages
    window_messages = _build_window(remaining_messages, max_messages)

    # Combine: system + window
    filtered_messages = (
        ([first_system_message] if first_system_message else [])
        + window_messages
    )

    # Remove trailing empty AIMessages
    filtered_messages = _trim_trailing_invalid_ai(filtered_messages)

    # Log token savings from filtering
    filtered_count = len(filtered_messages)
    filtered_tokens = _estimate_tokens(filtered_messages)
    saved_tokens = original_tokens - filtered_tokens
    saved_percentage = (
        (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
    )

    logger.info(
        "Message filter: %d → %d messages (~%d → ~%d tokens, saved ~%d tokens / %.1f%%)",
        original_count,
        filtered_count,
        original_tokens,
        filtered_tokens,
        saved_tokens,
        saved_percentage,
    )

    return filtered_messages


def sanitize_response(response: AIMessage) -> AIMessage:
    """Remove hallucinated tool calls that violate API constraints."""
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return response

    name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
    valid_tool_calls = []

    for tool_call in response.tool_calls:
        name = tool_call.get("name", "")
        if name_pattern.match(name) and len(name) < 64:
            valid_tool_calls.append(tool_call)
        else:
            logger.warning("SANITIZER: Removed invalid tool call with name: '%s'", name)

    response.tool_calls = valid_tool_calls
    return response
