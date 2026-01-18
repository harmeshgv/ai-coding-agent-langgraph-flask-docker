"""Helpers for filtering and sanitizing agent message histories."""

from __future__ import annotations

import logging
import re
from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

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


def _find_first_human_message(messages: list[BaseMessage]) -> int | None:
    """Find index of first HumanMessage (original task)."""
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            return idx
    return None


def _find_safe_start_boundary(messages: list[BaseMessage], recent_start_idx: int) -> int:
    """Find a safe starting point by scanning forward from the cutoff."""
    adjusted_start_idx = recent_start_idx

    for idx in range(recent_start_idx, len(messages)):
        msg = messages[idx]
        if isinstance(msg, (HumanMessage, AIMessage)):
            adjusted_start_idx = idx
            break

    return adjusted_start_idx


def _trim_trailing_invalid_ai_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Remove trailing AIMessages without tool_calls."""
    trimmed = list(messages)
    while trimmed and isinstance(trimmed[-1], AIMessage):
        ai_msg = trimmed[-1]
        if getattr(ai_msg, "tool_calls", None):
            break
        trimmed = trimmed[:-1]
    return trimmed


def _log_token_savings(
    original_count: int,
    original_tokens: int,
    filtered_count: int,
    filtered_tokens: int,
) -> None:
    """Log token savings statistics."""
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


def filter_messages_for_llm(
    messages: list[BaseMessage], max_messages: int = 10
) -> list[BaseMessage]:
    """Filter messages to keep only the most recent and relevant context."""
    if not messages:
        return []

    # Track original message count and token estimate for logging
    original_count = len(messages)
    original_tokens = _estimate_tokens(messages)

    # Extract and preserve all system messages
    # System messages contain critical instructions and must always be included
    system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
    non_system_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]

    # Find the first human message (original task) to preserve context
    first_human_idx = _find_first_human_message(non_system_messages)
    # Calculate starting index for recent messages window
    recent_start_idx = max(0, len(non_system_messages) - max_messages)
    # Adjust start boundary to ensure we begin at a valid message type
    adjusted_start_idx = _find_safe_start_boundary(non_system_messages, recent_start_idx)

    # Extract recent messages from the adjusted starting point
    recent_messages = non_system_messages[adjusted_start_idx:]
    # Remove trailing AI messages without tool calls (incomplete responses)
    recent_messages = _trim_trailing_invalid_ai_messages(recent_messages)

    # Fallback: if no recent messages remain, find the last human message or use the last message
    if not recent_messages and non_system_messages:
        for msg in reversed(non_system_messages):
            if isinstance(msg, HumanMessage):
                filtered_messages = [msg]
                break
        else:
            filtered_messages = [non_system_messages[-1]] if non_system_messages else []
    # If the first human message (original task) was cut off, prepend it to maintain context
    elif first_human_idx is not None and first_human_idx < adjusted_start_idx:
        first_task = [non_system_messages[first_human_idx]]
        filtered_messages = first_task + recent_messages
    # Otherwise, use only the recent messages
    else:
        filtered_messages = recent_messages

    # Prepend all system messages at the beginning
    filtered_messages = system_messages + filtered_messages

    # Log token savings from filtering
    filtered_count = len(filtered_messages)
    filtered_tokens = _estimate_tokens(filtered_messages)
    _log_token_savings(original_count, original_tokens, filtered_count, filtered_tokens)

    return filtered_messages


def sanitize_response(response: AIMessage) -> AIMessage:
    """Remove hallucinated tool calls that violate API constraints."""
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return response

    valid_tools: List[dict] = []
    name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

    for tool_call in response.tool_calls:
        name = tool_call.get("name", "")
        if name_pattern.match(name) and len(name) < 64:
            valid_tools.append(tool_call)
        else:
            logger.warning("SANITIZER: Removed invalid tool call with name: '%s'", name)

    response.tool_calls = valid_tools
    return response
