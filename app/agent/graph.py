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
from app.agent.nodes.checkout import create_checkout_node
from app.agent.nodes.coder import create_coder_node
from app.agent.nodes.explainer import create_explainer_node
from app.agent.nodes.pull_request import create_pull_request_node
from app.agent.nodes.router import create_router_node
from app.agent.nodes.task_fetch_node import create_task_fetch_node
from app.agent.nodes.task_update_node import create_task_update_node
from app.agent.nodes.tester import create_tester_node
from app.agent.runtime import RuntimeSetting
from app.agent.services.summaries import has_finish_task_call
from app.agent.state import AgentState
from app.agent.tools.add_task_comment import add_task_comment
from app.agent.tools.file_tools import (
    list_files,
    read_file,
    write_to_file,
)
from app.agent.tools.plan_tools import write_plan
from app.agent.tools.finish_task import finish_task
from app.agent.tools.run_command import run_command
from app.agent.tools.thinking import thinking
from app.agent.tools.report_test_result import report_test_result


def route_after_tools_tester(state: AgentState):
    """
    Routes flow after the tester's tools have run. Checks for a 'pass' result
    to finish, a 'fail' result to loop back to the coder, a 'error' result
    to end with error status, or loops back to the tester if other tools were used.
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
                if result == "error":
                    return "error"  # Environmental issue -> End with error
                # Failed -> Back to the coder
                return "failed"

    # If no 'report_test_result' was present (e.g., only 'run_command' or 'git_add')
    # then return to the tester (loop) so it can continue.
    return "tester"


def route_after_tools_coder(state: AgentState) -> str:
    """
    Decides AFTER the tools for Coder have run:
    - Was the last tool 'finish_task'? -> Continue to Tester.
    - Otherwise -> Loop back to the current agent.
    """
    messages = state["messages"]

    # 1. Determine who was active
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
    analyst_tools = [
        list_files,
        read_file,
        write_plan,
        thinking,
        add_task_comment,
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
        report_test_result,
    ]

    # --- Graph Nodes ---
    workflow = StateGraph(AgentState)

    workflow.add_node("task_fetch", create_task_fetch_node(runtime.agent_settings))
    workflow.add_node("checkout", create_checkout_node(runtime.agent_settings))
    workflow.add_node("router", create_router_node(runtime.llm_small))

    workflow.add_node(
        "coder", create_coder_node(runtime.llm_large, coder_tools, runtime.agent_stack)
    )
    workflow.add_node(
        "analyst",
        create_analyst_node(runtime.llm_large, analyst_tools),
    )

    workflow.add_node(
        "tester",
        create_tester_node(runtime.llm_large, tester_tools),
    )
    workflow.add_node("explainer", create_explainer_node(runtime.llm_large))

    # Tool Nodes
    workflow.add_node("tools_coder", ToolNode(coder_tools))
    workflow.add_node("tools_analyst", ToolNode(analyst_tools))
    workflow.add_node("tools_tester", ToolNode(tester_tools))

    workflow.add_node("pull_request", create_pull_request_node())
    workflow.add_node("task_update", create_task_update_node(runtime.agent_settings))

    workflow.set_entry_point("task_fetch")

    # --- Edges ---

    # 1. Start -> Router
    workflow.add_conditional_edges(
        "task_fetch",
        lambda state: "router" if state.get("provider_task") else END,
        {END: END, "router": "router"},
    )

    # 2. Router -> task_update (reject) or checkout (coder/analyst)
    def _route_router(state: AgentState) -> str:
        return "reject" if state.get("next_step") == "reject" else "coding | analyzing"

    workflow.add_conditional_edges(
        "router",
        _route_router,
        {
            "coding | analyzing": "checkout",
            "reject": "task_update",
        },
    )

    # 3. Checkout -> Specialists: Coder | Analyst
    def _route_checkout(state: AgentState) -> str:
        return "analyzing" if state.get("next_step") == "analyst" else "coding"

    workflow.add_conditional_edges(
        "checkout",
        _route_checkout,
        {
            "coding": "coder",
            "analyzing": "analyst",
        },
    )

    # 3. Specialists -> Tools (invoke_tool_node guarantees a tool call or fallback)
    workflow.add_edge("coder", "tools_coder")

    # 4. Analyst -> Analyst tools
    workflow.add_edge("analyst", "tools_analyst")

    # 5. ROUTING AFTER TOOLS

    # For Coder:
    # Check for finish_task -> Tester. Otherwise -> Back to agent (Loop).
    workflow.add_conditional_edges(
        "tools_coder",
        route_after_tools_coder,
        {
            "coder": "coder",  # Loop
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
            "pass": "explainer",  # Success
            "failed": "coder",  # Tests failed back to coder
            "error": "task_update",  # Environment issue -> surface to user
        },
    )

    workflow.add_edge("explainer", "pull_request")
    workflow.add_edge("pull_request", "task_update")
    workflow.add_edge("task_update", END)

    return workflow
