"""Tests for agent.core.graph.create_workflow wiring."""

from __future__ import annotations

from collections import OrderedDict

import pytest

import app.agent.graph as graph_module
from app.agent.runtime import RuntimeSetting
from app.core.models import AgentSettings


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
        "create_bugfixer_node",
        "create_checkout_node",
        "create_coder_node",
        "create_correction_node",
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
        "bugfixer",
        "analyst",
        "tester",
        "tools_coder",
        "tools_analyst",
        "tools_tester",
        "correction",
        "pull_request",
        "task_update",
    }

    assert set(workflow.nodes.keys()) == expected_nodes
    assert workflow.entry_point == "task_fetch"

    router_mapping = dict(
        next(
            mapping.items()
            for source, mapping in workflow.conditional_edges
            if source == "router"
        )  # type: ignore[stop-iteration]
    )
    assert router_mapping == {
        "reject": "task_update",
        "coder": "coder",
        "bugfixer": "bugfixer",
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
    assert {"coder", "bugfixer"}.issubset(tools_coder_mapping.keys())

    assert ("tester", "tools_tester") in workflow.edges
    assert ("pull_request", "task_update") in workflow.edges
