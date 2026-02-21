# pylint: disable=duplicate-code
"""
Defines the Bugfixer agent node for the agent graph.

The Bugfixer is a specialist agent responsible for debugging code, analyzing
errors, and implementing fixes for identified issues.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.agent.nodes.base import invoke_tool_node
from app.agent.services.prompts import load_prompt
from app.agent.services.summaries import has_finish_task_call, record_finish_task_summary
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_bugfixer_node(llm, tools):
    """
    Factory function that creates the Bugfixer agent node.

    Args:
        llm: The language model to be used by the bugfixer.
        tools: A list of tools available to the bugfixer.

    Returns:
        A function that represents the bugfixer node.
    """

    def _llm_response_hook(state: AgentState, response: AIMessage) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if has_finish_task_call(message=response):
            recorded, agent_summary = record_finish_task_summary(
                state=state, role="bugfixer", ai_message=response
            )
            if recorded:
                result["agent_summary"] = agent_summary

            result["user_message"] = (
                "Review the pull request. If you approve it, move the task to 'done'.\n"
                + "If you reject it, comment the task and move it to 'in progress'."
            )

        return result

    async def bugfixer_node(state: AgentState):

        if state["current_node"] != "bugfixer":
            logger.info("--- BUGFIXER node ---")

        system_message = load_prompt("systemprompt_bugfixer.md", state)
        human_message = load_prompt("prompt_coding.md", state)

        return await invoke_tool_node(  # pylint: disable=duplicate-code
            node_name="bugfixer",
            state=state,
            llm=llm,
            tools=tools,
            system_prompt=system_message,
            human_prompt=human_message,
            max_messages=15,
            fallback_tool_name="finish_task",
            fallback_tool_args={"summary": "Agent stuck."},
            llm_response_hook=_llm_response_hook,
        )

    return bugfixer_node
