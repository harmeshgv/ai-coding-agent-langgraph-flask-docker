"""
Defines the Tester agent node for the agent graph.

The Tester is a specialist agent responsible for verifying code changes,
running tests, and reporting the results.
"""

import logging
from typing import Any, Dict, Literal, Optional

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from agent.core.state import AgentState
from agent.services.logging import log_agent_response
from agent.services.message_processing import filter_messages_for_llm
from agent.services.prompts import load_system_prompt
from agent.services.summaries import append_agent_summary
from agent.tools.report_test_result import report_test_result

logger = logging.getLogger(__name__)


class TesterResult(BaseModel):
    """Call this tool ONLY when you have completed the testing process."""

    result: Literal["pass", "fail"] = Field(
        ...,
        description="The final result. 'pass' if tests and PR are successful, 'fail' otherwise.",
    )
    summary: str = Field(
        ...,
        description="A short summary of what happened (e.g. 'PR created at xyz' "
        + "or 'Tests failed because of NPE').",
    )


def create_tester_node(llm, tools, agent_stack):
    """
    Factory function that creates the Tester agent node.

    Args:
        llm: The language model to be used by the tester.
        tools: A list of tools available to the tester.
        agent_stack: The technology stack to load the correct system prompt.

    Returns:
        A function that represents the tester node.
    """
    sys_msg = load_system_prompt(agent_stack, "tester")
    llm_with_tools = llm.bind_tools(tools + [report_test_result])

    async def tester_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 15 messages)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages = [SystemMessage(content=sys_msg)] + filtered_messages

        response = await llm_with_tools.ainvoke(current_messages)

        has_content = bool(response.content)
        has_tool_calls = bool(getattr(response, "tool_calls", []))

        if has_content or has_tool_calls:
            log_agent_response("tester", response)

        summary_entries = list(state.get("agent_summary") or [])
        report_args = _get_report_result_args(response)

        if report_args and tests_passed(report_args):
            summary = report_args.get("summary", "")
            summary_entries = append_agent_summary(
                summary_entries,
                "tester",
                summary,
            )

        return {
            "messages": [response],
            "agent_summary": summary_entries,
        }

    return tester_node


def _get_report_result_args(response: Any) -> Optional[Dict[str, Any]]:
    """
    Returns the argument payload of the report_test_result tool call if present.
    """
    for tool_call in getattr(response, "tool_calls", []) or []:
        if tool_call.get("name") == "report_test_result":
            return tool_call.get("args", {})
    return None


def tests_passed(tool_args: Optional[Dict[str, Any]]) -> bool:
    """
    Determines whether the provided tool arguments represent a passing test run.
    """
    if not tool_args:
        return False
    result = tool_args.get("result")
    return isinstance(result, str) and result.lower() == "pass"
