"""
Defines the main agent workflow using LangGraph.

This module constructs a stateful graph that represents the agent's decision-making
process. It defines the nodes (different specialist agents like Coder, Tester),
the edges (the transitions between nodes), and the conditional logic that
routes the flow of execution based on the current state.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.nodes.analyst import create_analyst_node
from app.agent.nodes.bugfixer import create_bugfixer_node
from app.agent.nodes.checkout import create_checkout_node
from app.agent.nodes.coder import create_coder_node
from app.agent.nodes.correction import create_correction_node
from app.agent.nodes.pull_request import create_pull_request_node
from app.agent.nodes.router import create_router_node
from app.agent.nodes.task_fetch_node import create_task_fetch_node
from app.agent.nodes.task_update_node import create_task_update_node
from app.agent.nodes.tester import create_tester_node
from app.agent.runtime import RuntimeSetting
from app.agent.services.summaries import has_finish_task_call
from app.agent.state import AgentState
from app.agent.tools.create_task import create_task_tool
from app.agent.tools.file_tools import (
    list_files,
    read_file,
    write_to_file,
)
from app.agent.tools.finish_task import finish_task
from app.agent.tools.run_command import run_command
from app.agent.tools.thinking import thinking


def route_after_tools_tester(state: AgentState):
    """
    Routes flow after the tester's tools have run. Checks for a 'pass' result
    to finish, a 'fail' result to loop back to the coder/bugfixer, or loops
    back to the tester if other tools were used.
    """
    messages = state["messages"]

    # Ensure we have enough messages
    if len(messages) < 2:
        return "tester"

    # Look at the message BEFORE the tool output (the tester's AIMessage)
    last_ai_msg = messages[-2]

    if isinstance(last_ai_msg, AIMessage):
        # Only check valid parsed tool_calls that were actually executed
        tool_calls = last_ai_msg.tool_calls or []

        for tool_call in tool_calls:
            name = tool_call.get("name", "")
            if name == "report_test_result":
                args = tool_call.get("args", {})
                result = args.get("result") if isinstance(args, dict) else None

                if result == "pass":
                    return "pass"  # Success -> End
                # Failed -> Back to the handler
                previous_agent = state.get("next_step", "coder")
                return f"{previous_agent} failed"

    # If no 'report_test_result' was present (e.g., only 'run_command' or 'git_add')
    # then return to the tester (loop) so it can continue.
    return "tester"


def check_agent_exit(state: AgentState) -> str:
    """
    Checks after Coder/Bugfixer/Analyst:
    - Did the LLM choose a tool? -> tools
    - Did it output text? -> no tool (correction)
    """
    last_msg = state["messages"][-1]

    if not isinstance(last_msg, AIMessage):
        return "no tool"

    # Only valid parsed tool calls can be executed by ToolNode
    if last_msg.tool_calls:
        return "tools"

    # No valid tool calls (includes invalid_tool_cases) -> needs correction
    return "no tool"


def route_after_tools_coder(state: AgentState) -> str:
    """
    Decides AFTER the tools for Coder/Bugfixer have run:
    - Was the last tool 'finish_task'? -> Continue to Tester.
    - Otherwise -> Loop back to the current agent (Coder or Bugfixer).
    """
    messages = state["messages"]

    # 1. Determine who was active (Coder or Bugfixer)
    current_agent = state.get("next_step", "coder")

    # 2. Check for finish_task
    if len(messages) >= 2:
        ai_msg = messages[-2]  # The message BEFORE the tool output
        if has_finish_task_call(ai_msg):
            return "finish"

    # 3. No finish? Then loop back to the agent
    return current_agent


def route_after_tools_analyst(state: AgentState) -> str:
    """
    Special router for Analyst:
    - finish_task -> task_update (Not Tester!)
    - Otherwise -> Loop back to Analyst
    """
    messages = state["messages"]

    if len(messages) >= 2:
        ai_msg = messages[-2]
        if has_finish_task_call(ai_msg):
            return "finish"  # Goes to task_update

    return "analyst"


def create_workflow(runtime: RuntimeSetting) -> StateGraph:
    """Creates and configures the main LangGraph workflow."""
    # --- Tool Sets ---
    active_task_system = runtime.agent_settings.get_active_task_system()
    impl_task_target_state = (
        active_task_system.state_backlog if active_task_system else None
    )
    analyst_tools = [
        list_files,
        read_file,
        write_to_file,
        thinking,
        create_task_tool(runtime.agent_settings, impl_task_target_state),
        finish_task,
    ]
    coder_tools = [
        list_files,
        read_file,
        write_to_file,
        thinking,
        finish_task,
    ]
    tester_tools = [
        thinking,
        run_command,
    ]

    # --- Graph Nodes ---
    workflow = StateGraph(AgentState)

    workflow.add_node(
        "task_fetch", create_task_fetch_node(runtime.agent_settings)
    )
    workflow.add_node("checkout", create_checkout_node(runtime.agent_settings))
    workflow.add_node("router", create_router_node(runtime.llm_small))

    workflow.add_node(
        "coder", create_coder_node(runtime.llm_large, coder_tools, runtime.agent_stack)
    )
    workflow.add_node(
        "bugfixer",
        create_bugfixer_node(runtime.llm_large, coder_tools, runtime.agent_stack),
    )
    workflow.add_node(
        "analyst",
        create_analyst_node(runtime.llm_large, analyst_tools, runtime.agent_stack),
    )

    workflow.add_node(
        "tester",
        create_tester_node(runtime.llm_large, tester_tools, runtime.agent_stack),
    )

    # Tool Nodes
    workflow.add_node("tools_coder", ToolNode(coder_tools))
    workflow.add_node("tools_analyst", ToolNode(analyst_tools))
    workflow.add_node("tools_tester", ToolNode(tester_tools))

    workflow.add_node("correction", create_correction_node())
    workflow.add_node("pull_request", create_pull_request_node())
    workflow.add_node("task_update", create_task_update_node(runtime.agent_settings))

    workflow.set_entry_point("task_fetch")

    # --- Edges ---

    # 1. Start -> Router
    workflow.add_conditional_edges(
        "task_fetch",
        lambda state: "checkout" if state.get("task") else END,
        {END: END, "checkout": "checkout"},
    )

    workflow.add_edge("checkout", "router")

    # 2. Router -> Specialists: Coder | Bugfixer | Analyst
    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("next_step", "coder"),
        {
            "reject": "task_update",
            "coder": "coder",
            "bugfixer": "bugfixer",
            "analyst": "analyst",
        },
    )

    # 3. Coder -> Tools | Correction
    workflow.add_conditional_edges(
        "coder",
        check_agent_exit,
        {
            "tools": "tools_coder",
            "no tool": "correction",
        },
    )

    # 4. Bugfixer -> Tools | Correction
    workflow.add_conditional_edges(
        "bugfixer",
        check_agent_exit,
        {
            "tools": "tools_coder",
            "no tool": "correction",
        },
    )

    # 5. Analyst -> Tools | Correction
    workflow.add_conditional_edges(
        "analyst",
        check_agent_exit,
        {
            "tools": "tools_analyst",
            "no tool": "correction",
        },
    )

    # 6. ROUTING AFTER TOOLS

    # For Coder & Bugfixer:
    # Check for finish_task -> Tester. Otherwise -> Back to agent (Loop).
    workflow.add_conditional_edges(
        "tools_coder",
        route_after_tools_coder,
        {
            "coder": "coder",  # Loop
            "bugfixer": "bugfixer",  # Loop
            "finish": "tester",  # Exit to Tester
        },
    )

    # For Analyst:
    # Check for finish_task -> Task Update. Otherwise -> Loop.
    workflow.add_conditional_edges(
        "tools_analyst",
        route_after_tools_analyst,
        {"analyst": "analyst", "finish": "task_update"},
    )

    # 7. Tester Logic
    # 7.1. Tester -> Tools
    workflow.add_edge("tester", "tools_tester")

    # 7.2. Tools -> Decision
    workflow.add_conditional_edges(
        "tools_tester",
        route_after_tools_tester,
        {
            "tester": "tester",  # Loop (for git, mvn)
            "pass": "pull_request",  # Success
            "coder failed": "coder",  # Tests failed back to coder or bugfixer
            "bugfixer failed": "bugfixer",
        },
    )

    # 8. Correction & End
    workflow.add_conditional_edges(
        "correction",
        lambda state: state.get("next_step"),
        {"coder": "coder", "bugfixer": "bugfixer", "analyst": "analyst"},
    )

    workflow.add_edge("pull_request", "task_update")
    workflow.add_edge("task_update", END)

    return workflow
