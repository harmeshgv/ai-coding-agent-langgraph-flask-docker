"""Unit tests for agent.summaries helpers."""

from __future__ import annotations

from itertools import count

from langchain_core.messages import AIMessage

from app.agent.models import AgentSummary
from app.agent.services.summaries import (
    append_agent_summary,
    get_agent_summary_entries,
    record_finish_task_summary,
)

_TOOL_CALL_COUNTER = count()


def _tool_call(name: str, args: dict | None = None) -> dict:
    return {
        "id": f"tool-call-{next(_TOOL_CALL_COUNTER)}",
        "name": name,
        "args": args or {},
    }


def test_append_agent_summary_ignores_empty_entries():
    entries = [AgentSummary(role="coder", summary="Did work")]
    result = append_agent_summary(entries.copy(), "coder", "   ")
    assert result == entries


def test_record_finish_task_summary_updates_state_and_tool_args():
    state = {"agent_summary": []}
    ai_message = AIMessage(
        content="",
        tool_calls=[
            _tool_call("finish_task", {"summary": "All done"}),
        ],
    )

    recorded, summary_entries = record_finish_task_summary(state, "coder", ai_message)

    assert recorded is True
    assert len(summary_entries) == 1
    assert summary_entries[0].role == "coder"
    assert summary_entries[0].summary == "All done"
    assert state["agent_summary"] == summary_entries
    assert ai_message.tool_calls[0]["args"]["agent_role"] == "coder"


def test_get_agent_summary_entries_derives_from_messages_when_cache_empty():
    ai_message = AIMessage(
        content="",
        tool_calls=[
            _tool_call(
                "finish_task", {"summary": "Task complete", "agent_role": "tester"}
            ),
        ],
    )
    state = {"messages": [ai_message]}

    entries = get_agent_summary_entries(state)
    assert len(entries) == 1
    assert entries[0].role == "tester"
    assert entries[0].summary == "Task complete"


def test_get_agent_summary_entries_deduplicates_consecutive_entries():
    state = {
        "agent_summary": [
            AgentSummary(role="coder", summary="Implemented divide method"),
            AgentSummary(role="tester", summary="All tests passed"),
            AgentSummary(role="tester", summary="All tests passed"),
        ]
    }

    entries = get_agent_summary_entries(state)

    assert len(entries) == 2
    assert entries[0].role == "coder"
    assert entries[0].summary == "Implemented divide method"
    assert entries[1].role == "tester"
    assert entries[1].summary == "All tests passed"
