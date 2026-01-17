"""
Defines the main agent workflow using LangGraph.

This module constructs a stateful graph that represents the agent's decision-making
process. It defines the nodes (different specialist agents like Coder, Tester),
the edges (the transitions between nodes), and the conditional logic that
routes the flow of execution based on the current state.
"""

from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes.agent_skill_level import create_agent_skill_level_node
from agent.nodes.analyst import create_analyst_node
from agent.nodes.bugfixer import create_bugfixer_node
from agent.nodes.checkout import create_checkout_node
from agent.nodes.coder import create_coder_node
from agent.nodes.correction import create_correction_node
from agent.nodes.pull_request import create_pull_request_node
from agent.nodes.router import create_router_node
from agent.nodes.tester import create_tester_node
from agent.nodes.trello_fetch_node import create_trello_fetch_node
from agent.nodes.trello_update_node import create_trello_update_node
from agent.services.summaries import has_finish_task_call
from agent.state import AgentState
from agent.tools.create_issue import create_issue_tool
from agent.tools.file_tools import (
    list_files,
    read_file,
    write_to_file,
)
from agent.tools.finish_task import finish_task
from agent.tools.run_command import run_command
from agent.tools.thinking import thinking


def route_after_tools_tester(state: AgentState):
    """
    Routes flow after the tester's tools have run. Checks for a 'pass' result
    to finish, a 'fail' result to loop back to the coder/bugfixer, or loops
    back to the tester if other tools were used.
    """
    messages = state["messages"]

    # Sicherstellen, dass wir genug Nachrichten haben
    if len(messages) < 2:
        return "tester"

    # Wir schauen auf die Nachricht VOR dem Tool-Output (die AIMessage des Testers)
    last_ai_msg = messages[-2]

    if isinstance(last_ai_msg, AIMessage) and last_ai_msg.tool_calls:
        # Wir iterieren durch ALLE Tool Calls, falls der Agent mehrere gemacht hat
        for tool_call in last_ai_msg.tool_calls:
            if tool_call["name"] == "report_test_result":
                args = tool_call["args"]
                result = args.get("result")

                if result == "pass":
                    return "pass"  # Erfolg -> Ende
                # Fehlgeschlagen -> Zurück zum Bearbeiter
                previous_agent = state.get("next_step", "coder")
                return f"{previous_agent} failed"

    # Wenn kein 'report_test_result' dabei war (z.B. nur 'run_command' oder 'git_add')
    # dann geht es zurück zum Tester (Loop), damit er weitermachen kann.
    return "tester"


def check_agent_exit(state: AgentState) -> str:
    """
    Prüft nach Coder/Bugfixer/Analyst:
    - Hat das LLM ein Tool gewählt? -> tools
    - Hat es Text gelabert? -> no tool (Korrektur)
    """
    last_msg = state["messages"][-1]

    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return "no tool"

    # Wir führen ALLE Tools aus, auch finish_task
    return "tools"


def route_after_tools_coder(state: AgentState) -> str:
    """
    Entscheidet NACHDEM die Tools für Coder/Bugfixer liefen:
    - War das letzte Tool 'finish_task'? -> Weiter zum Tester.
    - Sonst -> Loop zurück zum aktuellen Agenten (Coder oder Bugfixer).
    """
    messages = state["messages"]

    # 1. Bestimmen, wer gerade dran war (Coder oder Bugfixer)
    current_agent = state.get("next_step", "coder")

    # 2. Prüfen auf finish_task
    if len(messages) >= 2:
        ai_msg = messages[-2]  # Die Nachricht VOR dem Tool-Output
        if has_finish_task_call(ai_msg):
            return "finish"

    # 3. Kein Finish? Dann Loop zurück zum Agenten
    return current_agent


def route_after_tools_analyst(state: AgentState) -> str:
    """
    Spezial-Router für Analyst:
    - finish_task -> task_update (Nicht Tester!)
    - Sonst -> Loop zurück zum Analyst
    """
    messages = state["messages"]

    if len(messages) >= 2:
        ai_msg = messages[-2]
        if has_finish_task_call(ai_msg):
            return "finish"  # Geht zu task_update

    return "analyst"


def create_workflow(
    llm_large: BaseChatModel,
    llm_small: BaseChatModel,
    sys_config: dict,
    agent_stack: str,
) -> StateGraph:
    """Creates and configures the main LangGraph workflow."""
    # --- Tool Sets ---
    impl_issue_target_list = sys_config.get("backlog_list")
    analyst_tools = [
        list_files,
        read_file,
        thinking,
        create_issue_tool(sys_config, impl_issue_target_list),
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

    workflow.add_node("task_fetch", create_trello_fetch_node(sys_config))
    workflow.add_node("checkout", create_checkout_node(sys_config))
    workflow.add_node("router", create_router_node(llm_small))
    workflow.add_node("agent_skill_level", create_agent_skill_level_node(llm_small))

    workflow.add_node("coder", create_coder_node(llm_large, coder_tools, agent_stack))
    workflow.add_node(
        "bugfixer", create_bugfixer_node(llm_large, coder_tools, agent_stack)
    )
    workflow.add_node(
        "analyst", create_analyst_node(llm_large, analyst_tools, agent_stack)
    )

    workflow.add_node(
        "tester", create_tester_node(llm_large, tester_tools, agent_stack)
    )

    # Tool Nodes
    workflow.add_node("tools_coder", ToolNode(coder_tools))
    workflow.add_node("tools_analyst", ToolNode(analyst_tools))
    workflow.add_node("tools_tester", ToolNode(tester_tools))

    workflow.add_node("correction", create_correction_node())
    workflow.add_node("pull_request", create_pull_request_node())
    workflow.add_node("task_update", create_trello_update_node(sys_config))

    workflow.set_entry_point("task_fetch")

    # --- Edges ---

    # 1. Start -> Router
    workflow.add_conditional_edges(
        "task_fetch",
        lambda state: "checkout" if state.get("trello_card_id") else END,
        {END: END, "checkout": "checkout"},
    )

    workflow.add_edge("checkout", "router")

    # 2. Router -> Spezialisten: Coder | Bugfixer | Analyst
    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("next_step", "coder"),
        {"coder": "agent_skill_level", "bugfixer": "bugfixer", "analyst": "analyst"},
    )

    # 2a. Skill level -> Coder | Task_update
    workflow.add_conditional_edges(
        "agent_skill_level",
        lambda state: state["task_skill_level"] == "junior"
        or state["agent_skill_level"] == "senior",
        {True: "coder", False: "task_update"},
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

    # 6. ROUTING NACH DEN TOOLS

    # Für Coder & Bugfixer:
    # Prüft auf finish_task -> Tester. Sonst -> Zurück zum Agenten (Loop).
    workflow.add_conditional_edges(
        "tools_coder",
        route_after_tools_coder,
        {
            "coder": "coder",  # Loop
            "bugfixer": "bugfixer",  # Loop
            "finish": "tester",  # Exit zu Tester
        },
    )

    # Für Analyst:
    # Prüft auf finish_task -> Task Update. Sonst -> Loop.
    workflow.add_conditional_edges(
        "tools_analyst",
        route_after_tools_analyst,
        {"analyst": "analyst", "finish": "task_update"},
    )

    # 7. Tester Logik
    # 7.1. Tester -> Tools
    workflow.add_edge("tester", "tools_tester")

    # 7.2. Tools -> Entscheidung
    workflow.add_conditional_edges(
        "tools_tester",
        route_after_tools_tester,
        {
            "tester": "tester",  # Loop (für git, mvn)
            "pass": "pull_request",  # Erfolg
            "coder failed": "coder",  # Tests failed back to coder or bugfixer
            "bugfixer failed": "bugfixer",
        },
    )

    # 8. Correction & Ende
    workflow.add_conditional_edges(
        "correction",
        lambda state: state.get("next_step"),
        {"coder": "coder", "bugfixer": "bugfixer", "analyst": "analyst"},
    )

    workflow.add_edge("pull_request", "task_update")
    workflow.add_edge("task_update", END)

    return workflow
