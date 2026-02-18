"""
Defines the Tester agent node for the agent graph.

The Tester is a specialist agent responsible for verifying code changes,
running tests, and reporting the results.
"""  # pylint: disable=duplicate-code

import logging
from typing import Any, Dict, Literal, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.services.logging import log_agent_response
from app.agent.services.message_processing import filter_messages_for_llm
from app.agent.services.prompts import load_prompt
from app.agent.services.summaries import append_agent_summary
from app.agent.state import AgentState
from app.agent.tools.report_test_result import report_test_result

logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
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


def create_tester_node(llm, tools):
    """
    Factory function that creates the Tester agent node.

    Args:
        llm: The language model to be used by the tester.
        tools: A list of tools available to the tester.

    Returns:
        A function that represents the tester node.
    """

    async def tester_node(state: AgentState):  # pylint: disable=too-many-locals
        if state["current_node"] != "tester":
            logger.info("--- TESTER node ---")
        system_message = load_prompt("systemprompt_tester.md", state)
        human_message = load_prompt("prompt_testing.md", state)
        # Filter messages to keep only recent relevant context (original task + last 15 messages)
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=15)
        current_messages: list[BaseMessage | SystemMessage | HumanMessage] = [
            SystemMessage(content=system_message),
            HumanMessage(content=human_message),
        ]

        current_messages += filtered_messages
        current_tool_choice = "auto"

        for attempt in range(3):
            try:
                chain = llm.bind_tools(
                    tools + [report_test_result], tool_choice=current_tool_choice
                )
                response = await chain.ainvoke(current_messages)

                has_tool_calls = bool(getattr(response, "tool_calls", []))

                if has_tool_calls:
                    log_agent_response("tester", response, attempt=attempt + 1)

                    summary_entries = list(state.get("agent_summary") or [])
                    report_args = _get_report_result_args(response)

                    if report_args and tests_passed(report_args):
                        summary = report_args.get("summary", "")
                        summary_entries = append_agent_summary(
                            summary_entries,
                            "tester",
                            summary,
                        )

                    result = {
                        "messages": [response],
                        "current_node": "tester",
                        "prompt": human_message,
                        "system_prompt": system_message,
                    }
                    if summary_entries:
                        result["agent_summary"] = summary_entries
                    return result

                logger.warning("Attempt %d: No tool calls. Escalating strategy...", attempt + 1)
                # Add the invalid response so AI sees its mistake
                current_messages.append(response)
                current_messages.append(
                    HumanMessage(
                        content="ERROR: Invalid response. You MUST call a tool. "
                        + "Use 'report_test_result' with the test results NOW."
                    )
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in LLM call (Attempt %d): %s", attempt + 1, e)

        # Fallback
        logger.error("Agent stuck after 3 attempts. Hard exit.")

        fallback_message = AIMessage(
            content="Testing stuck.",
            tool_calls=[
                {
                    "name": "report_test_result",
                    "args": {
                        "result": "fail",
                        "summary": "Testing could not complete due to invalid responses.",
                    },
                    "id": "call_emergency",
                    "type": "tool_call",
                }
            ],
        )

        summary_entries = list(state.get("agent_summary") or [])

        return {
            "messages": [fallback_message],
            "agent_summary": summary_entries,
            "current_node": "tester",
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
