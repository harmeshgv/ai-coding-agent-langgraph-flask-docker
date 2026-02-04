"""Unit tests for agent.message_processing helpers."""

from __future__ import annotations

from itertools import count

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.services.message_processing import (
    filter_messages_for_llm,
    sanitize_response,
)

_TOOL_CALL_COUNTER = count()


def _tool_call(name: str, args: dict | None = None) -> dict:
    return {
        "id": f"tool-call-{next(_TOOL_CALL_COUNTER)}",
        "name": name,
        "args": args or {},
    }


def _ai(content: str, *, tool_calls: list[dict] | None = None) -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _tool(tool_call_id: str, content: str = "result") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=tool_call_id)


def test_filter_messages_keeps_recent_window():
    """Should keep the most recent non-system messages up to the limit."""
    messages = [HumanMessage(content="Original Task")]
    for i in range(5):
        messages.append(_ai(f"assistant-{i}", tool_calls=[_tool_call("tool")]))
        messages.append(HumanMessage(content=f"user-{i}"))

    filtered = filter_messages_for_llm(messages, max_messages=4)

    assert [msg.content for msg in filtered] == [
        "assistant-3",
        "user-3",
        "assistant-4",
        "user-4",
    ]


def test_filter_messages_preserves_system_prefix():
    """System message stays pinned even though recent window shifts."""
    messages = [SystemMessage(content="System prompt")]
    messages.append(HumanMessage(content="Original Task"))
    for i in range(5):
        messages.append(_ai(f"assistant-{i}", tool_calls=[_tool_call("tool")]))
        messages.append(HumanMessage(content=f"user-{i}"))

    filtered = filter_messages_for_llm(messages, max_messages=4)

    assert isinstance(filtered[0], SystemMessage)
    assert filtered[0].content == "System prompt"
    assert [msg.content for msg in filtered[1:]] == [
        "assistant-3",
        "user-3",
        "assistant-4",
        "user-4",
    ]


def test_filter_messages_keeps_additional_system_messages_in_window():
    """SystemMessages beyond the first remain when within the window."""
    messages = [
        SystemMessage(content="Primary system"),
        HumanMessage(content="Task"),
        SystemMessage(content="Secondary system"),
        HumanMessage(content="Follow up"),
        HumanMessage(content="Another"),
    ]

    filtered = filter_messages_for_llm(messages, max_messages=5)

    assert len(filtered) == 5
    assert isinstance(filtered[0], SystemMessage)
    assert filtered[0].content == "Primary system"
    assert any(
        isinstance(msg, SystemMessage) and msg.content == "Secondary system"
        for msg in filtered[1:]
    ), "Additional SystemMessages within the window should be preserved"


def test_filter_messages_empty_input():
    """Should handle empty message list."""
    filtered = filter_messages_for_llm([], max_messages=10)
    assert filtered == []


def test_filter_messages_respects_max_messages():
    """Should keep only the latest messages within the cap."""
    messages = [HumanMessage(content="Task")]
    for i in range(20):
        messages.append(HumanMessage(content=f"message-{i}"))

    filtered = filter_messages_for_llm(messages, max_messages=5)
    assert len(filtered) == 5
    assert [msg.content for msg in filtered] == [
        "message-15",
        "message-16",
        "message-17",
        "message-18",
        "message-19",
    ]


def test_filter_messages_does_not_modify_messages():
    """Should not modify message content or structure."""
    msgs = [
        HumanMessage(content="Task"),
        _ai("", tool_calls=[]),  # Empty AI message
        HumanMessage(content="Follow up"),
    ]

    filtered = filter_messages_for_llm(msgs, max_messages=10)

    # Should preserve all messages without modification
    assert len(filtered) == 3
    assert isinstance(filtered[1], AIMessage)
    assert filtered[1].content == ""
    assert filtered[1].tool_calls == []


def test_filter_preserves_tool_call_pairs():
    """When cutting would orphan a ToolMessage, extend to include the AIMessage."""
    tc = _tool_call("my_tool")
    msgs = [
        HumanMessage(content="Task"),
        _ai("I will call a tool", tool_calls=[tc]),
        _tool(tc["id"], "result"),
        HumanMessage(content="Next"),
    ]

    # With max_messages=4: first human + last 3 messages
    # Window starts at "Next" but should extend back to include tool pair
    filtered = filter_messages_for_llm(msgs, max_messages=4)
    
    # Should have: Task + AI + Tool + Next
    assert len(filtered) == 4
    assert isinstance(filtered[1], AIMessage)
    assert filtered[1].tool_calls[0]["name"] == "my_tool"
    assert isinstance(filtered[2], ToolMessage)


def test_filter_removes_trailing_empty_ai():
    """Empty trailing AIMessages should be removed."""
    msgs = [
        HumanMessage(content="Task"),
        _ai("response"),
        _ai(""),  # Empty at end
    ]

    filtered = filter_messages_for_llm(msgs, max_messages=10)
    
    # Empty trailing AI should be removed
    assert len(filtered) == 2
    assert filtered[-1].content == "response"


def test_filter_keeps_trailing_ai_with_content():
    """Trailing AIMessages with content should be preserved."""
    msgs = [
        HumanMessage(content="Task"),
        _ai("response with content"),
    ]

    filtered = filter_messages_for_llm(msgs, max_messages=10)
    
    assert len(filtered) == 2
    assert filtered[-1].content == "response with content"


def test_filter_keeps_trailing_ai_with_tool_calls():
    """Trailing AIMessages with tool_calls should be preserved (and their ToolMessages)."""
    tc = _tool_call("finish_task")
    msgs = [
        HumanMessage(content="Task"),
        _ai("", tool_calls=[tc]),
        _tool(tc["id"], "done"),
    ]

    filtered = filter_messages_for_llm(msgs, max_messages=10)
    
    # Should preserve the complete tool sequence
    assert len(filtered) == 3
    assert isinstance(filtered[1], AIMessage)
    assert filtered[1].tool_calls[0]["name"] == "finish_task"


def test_filter_messages_no_human_warning():
    """Should log warning and return entire stack if no HumanMessage found."""
    msgs = [
        SystemMessage(content="System prompt"),
        _ai("AI response", tool_calls=[_tool_call("tool")]),
        _tool("tool-call-0", "result"),
    ]

    filtered = filter_messages_for_llm(msgs, max_messages=10)
    
    # Should return entire stack unchanged
    assert len(filtered) == 3
    assert isinstance(filtered[0], SystemMessage)
    assert isinstance(filtered[1], AIMessage)
    assert isinstance(filtered[2], ToolMessage)


def test_sanitize_response_removes_invalid_tool_calls():
    ai_msg = _ai(
        "",
        tool_calls=[_tool_call("finish_task"), _tool_call("invalid name")],
    )

    sanitized = sanitize_response(ai_msg)
    assert len(sanitized.tool_calls) == 1
    assert sanitized.tool_calls[0]["name"] == "finish_task"
