"""Tests for agent.core.graph.create_workflow wiring."""

from __future__ import annotations

from collections import OrderedDict

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import app.agent.graph as graph_module
from app.agent.graph import route_after_tools_tester
from app.agent.runtime import RuntimeSetting
from app.core.localdb.models import AgentSettings


def _make_ai_message(with_tool_calls: bool) -> AIMessage:
    if with_tool_calls:
        return AIMessage(
            content="",
            tool_calls=[{"name": "thinking", "args": {}, "id": "call_1", "type": "tool_call"}],
        )
    return AIMessage(content="plain text")


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "next_step": "coder",
        "current_node": "coder",
    }
    state.update(overrides)
    return state


class TestRouteAfterToolsTester:
    def _make_report_test_result_msg(self, result: str) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "report_test_result",
                    "args": {"result": result},
                    "id": "call_report",
                    "type": "tool_call",
                }
            ],
        )

    def test_routes_to_pass_on_success(self):
        ai_msg = self._make_report_test_result_msg("pass")
        state = _base_state(messages=[ai_msg, HumanMessage(content="tool output")])
        assert route_after_tools_tester(state) == "pass"

    def test_uses_current_node_not_next_step_on_failure(self):
        """Regression: stale next_step must not override the active agent on test failure."""
        ai_msg = self._make_report_test_result_msg("fail")
        state = _base_state(
            messages=[ai_msg, HumanMessage(content="tool output")],
            next_step="coder",
        )
        assert route_after_tools_tester(state) == "failed"

    def test_routes_back_to_coder_failed_when_coder_was_active(self):
        ai_msg = self._make_report_test_result_msg("fail")
        state = _base_state(
            messages=[ai_msg, HumanMessage(content="tool output")],
            current_node="coder",
        )
        assert route_after_tools_tester(state) == "failed"

    def test_loops_tester_when_no_report_test_result(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "run_command", "args": {}, "id": "call_run", "type": "tool_call"}],
        )
        state = _base_state(messages=[ai_msg, HumanMessage(content="tool output")])
        assert route_after_tools_tester(state) == "tester"

    def test_loops_tester_when_messages_too_short(self):
        state = _base_state(messages=[HumanMessage(content="only one")])
        assert route_after_tools_tester(state) == "tester"


class RecordingStateGraph:
    def __init__(self, state_type):
        self.state_type = state_type
        self.nodes = OrderedDict()
        self.edges = []
        self.conditional_edges = []
        self.entry_point = None

    def add_node(self, name, node):
        self.nodes[name] = node

    def add_edge(self, start, end):
        self.edges.append((start, end))

    def add_conditional_edges(self, source, condition, mapping):
        self.conditional_edges.append((source, mapping))

    def set_entry_point(self, name):
        self.entry_point = name

    def compile(self):  # pragma: no cover - not used by this test
        return object()


class DummyLLM:
    def bind_tools(self, tools, tool_choice="auto"):
        return self

    async def ainvoke(self, messages):  # pragma: no cover - not used
        return messages


@pytest.fixture()
def workflow_mocks(monkeypatch):
    monkeypatch.setattr(graph_module, "StateGraph", RecordingStateGraph)

    def _stub_factory(*_args, **_kwargs):
        async def _node(state):  # pragma: no cover - not invoked here
            return state

        return _node

    factories = [
        "create_analyst_node",
        "create_checkout_node",
        "create_coder_node",
        "create_pull_request_node",
        "create_router_node",
        "create_tester_node",
        "create_task_fetch_node",
        "create_task_update_node",
    ]
    originals = {}
    for name in factories:
        originals[name] = getattr(graph_module, name)
        monkeypatch.setattr(graph_module, name, _stub_factory)

    yield

    for name, original in originals.items():
        monkeypatch.setattr(graph_module, name, original)


def test_create_workflow_registers_all_nodes(workflow_mocks):
    llm_large = DummyLLM()
    llm_small = DummyLLM()
    agent_settings = AgentSettings(
        task_system_type="TRELLO",
        task_readfrom_state="todo",
    )

    runtime = RuntimeSetting(
        agent_settings=agent_settings,
        agent_stack="backend",
        mcp_system_def={},
        llm_large=llm_large,
        llm_small=llm_small,
    )

    workflow = graph_module.create_workflow(runtime)

    expected_nodes = {
        "task_fetch",
        "checkout",
        "router",
        "coder",
        "analyst",
        "tester",
        "tools_coder",
        "tools_analyst",
        "tools_tester",
        "pull_request",
        "task_update",
    }

    assert set(workflow.nodes.keys()) == expected_nodes
    assert workflow.entry_point == "task_fetch"

    router_mapping = dict(
        next(
            mapping.items() for source, mapping in workflow.conditional_edges if source == "router"
        )  # type: ignore[stop-iteration]
    )
    assert router_mapping == {
        "reject": "task_update",
        "coder": "coder",
        "analyst": "analyst",
    }

    tools_coder_mapping = dict(
        next(
            mapping.items()
            for source, mapping in workflow.conditional_edges
            if source == "tools_coder"
        )
    )
    assert tools_coder_mapping["finish"] == "tester"
    assert {"coder"}.issubset(tools_coder_mapping.keys())

    assert ("tester", "tools_tester") in workflow.edges
    assert ("pull_request", "task_update") in workflow.edges
