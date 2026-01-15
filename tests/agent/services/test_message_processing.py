"""Unit tests for agent.message_processing helpers."""

from __future__ import annotations

from itertools import count

from langchain_core.messages import AIMessage, HumanMessage

from agent.services.message_processing import filter_messages_for_llm, sanitize_response


_TOOL_CALL_COUNTER = count()


def _tool_call(name: str, args: dict | None = None) -> dict:
    return {"id": f"tool-call-{next(_TOOL_CALL_COUNTER)}", "name": name, "args": args or {}}


def _ai(content: str, *, tool_calls: list[dict] | None = None) -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def test_filter_messages_preserves_task_and_recent_history():
    messages = [HumanMessage(content="Task")]
    for i in range(5):
        messages.append(_ai(f"assistant-{i}", tool_calls=[_tool_call("tool")]))
        messages.append(HumanMessage(content=f"user-{i}"))

    filtered = filter_messages_for_llm(messages, max_messages=3)

    assert filtered[0].content == "Task"
    assert len(filtered) == 4  # task + last 3 entries
    assert filtered[-1].content == "user-4"


def test_filter_messages_drops_trailing_ai_without_tools():
    msgs = [HumanMessage(content="Task"), _ai("assistant", tool_calls=[_tool_call("tool")])]
    msgs.append(_ai("orphan"))

    filtered = filter_messages_for_llm(msgs, max_messages=2)
    assert all(not (isinstance(msg, AIMessage) and not msg.tool_calls) for msg in filtered[-1:])


def test_sanitize_response_removes_invalid_tool_calls():
    ai_msg = _ai(
        "",
        tool_calls=[_tool_call("finish_task"), _tool_call("invalid name")],
    )

    sanitized = sanitize_response(ai_msg)
    assert len(sanitized.tool_calls) == 1
    assert sanitized.tool_calls[0]["name"] == "finish_task"
