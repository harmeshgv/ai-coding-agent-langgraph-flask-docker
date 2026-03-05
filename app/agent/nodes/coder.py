# pylint: disable=duplicate-code
"""
Defines the Coder agent node for the agent graph.

The Coder is a specialist agent responsible for writing new code, creating
files, and implementing features based on the task requirements.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.agent.nodes.base import invoke_tool_node
from app.agent.services.prompts import load_prompt
from app.agent.services.summaries import has_finish_task_call, record_finish_task_summary
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_coder_node(llm, tools, agent_stack):
    """
    Factory function that creates the Coder agent node.

    Args:
        llm: The language model to be used by the coder.
        tools: A list of tools available to the coder.
        agent_stack: The technology stack to load the correct system prompt.

    Returns:
        A function that represents the coder node.
    """

    def _llm_response_hook(state: AgentState, response: AIMessage) -> dict[str, Any]:
        result: dict[str, Any] = {}

        if has_finish_task_call(message=response):
            role = "coder" if state["agent_task"].task_type == "bugfix" else "coder"

            recorded, agent_summary = record_finish_task_summary(
                state=state, role=role, ai_message=response
            )
            if recorded:
                result["agent_summary"] = agent_summary

            result["user_message"] = (
                "Review the pull request. If you approve it, move the task to 'done'.\n"
                + "If you reject it, comment the task and move it to 'in progress'."
            )

        return result

    async def coder_node(state: AgentState):
        if state["current_node"] != "coder":
            logger.info("--- CODER node ---")
        system_message = (
            load_prompt(f"systemprompt_coder_{agent_stack}.md", state)
            if state["agent_task"].task_type == "coding"
            else load_prompt("systemprompt_bugfixer.md", state)
        )
        human_message = load_prompt("prompt_coding.md", state)
        return await invoke_tool_node(
            node_name="coder",
            state=state,
            llm=llm,
            tools=tools,
            system_prompt=system_message,
            human_prompt=human_message,
            max_messages=25,
            fallback_tool_name="finish_task",
            fallback_tool_args={"summary": "Agent stuck."},
            llm_response_hook=_llm_response_hook,
        )

    return coder_node
