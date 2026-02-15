"""Shared logging helpers for agent responses and state snapshots."""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage

logger = logging.getLogger(__name__)

__all__ = ["log_agent_response", "log_agent_state", "safe_truncate"]


def safe_truncate(value: Any, length: int = 100) -> str:
    """Convert any value to string, truncate, and collapse newlines."""
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
    """Log LLM responses consistently across nodes."""
    header = f"\n=== {agent_name.upper()} RESPONSE"
    if attempt is not None:
        header += f" (Attempt {attempt})"
    header += " ==="
    # logger.info(header)

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


def _log_message_detail(idx: int, message: BaseMessage, content_limit: int) -> None:
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


def _log_additional_kwargs(message: BaseMessage, arg_limit: int) -> None:
    additional_kwargs = getattr(message, "additional_kwargs", {})
    if additional_kwargs:
        logger.info("     additional_kwargs:")
        for key, value in additional_kwargs.items():
            logger.info("         %s: %s", key, safe_truncate(value, arg_limit))


def _log_tool_calls(message: BaseMessage, arg_limit: int) -> None:
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
    """Log a snapshot of the AgentState, including a detailed message dump."""
    logger.info("\n=== AGENT STATE SNAPSHOT ===")
    logger.info("next_step         : %s", state.get("next_step"))
    logger.info("agent_stack       : %s", state.get("agent_stack"))
    logger.info("retry_count       : %s", state.get("retry_count"))
    logger.info("test_result       : %s", state.get("test_result"))
    logger.info("error_log         : %s", state.get("error_log"))
    logger.info("task_id           : %s", state.get("task").id if state.get("task") else None)
    logger.info("task_state_id     : %s", state.get("task_state_id"))

    messages = state.get("messages", [])
    logger.info("\n--- Messages (%d) ---", len(messages))
    for idx, message in enumerate(messages, start=1):
        _log_message_detail(idx, message, content_limit)
        _log_additional_kwargs(message, arg_limit)
        _log_tool_calls(message, arg_limit)

    logger.info("=== END OF STATE SNAPSHOT ===")
