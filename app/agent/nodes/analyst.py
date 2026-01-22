"""
Defines the Analyst agent node for the agent graph.

The Analyst is a specialist agent responsible for analyzing code, answering
questions about the codebase, and providing explanations without making
any modifications.
"""

import logging
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from app.agent.services.logging import log_agent_response
from app.agent.services.message_processing import (
    filter_messages_for_llm,
    sanitize_response,
)
from app.agent.services.prompts import load_system_prompt
from app.agent.services.summaries import record_finish_task_summary
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_analyst_node(llm: BaseChatModel, tools, agent_stack):
    """
    Factory function that creates the Analyst agent node.

    Args:
        llm: The language model to be used by the analyst.
        tools: A list of tools available to the analyst.
        agent_stack: The technology stack (e.g., 'backend', 'frontend')
                     to load the correct system prompt.

    Returns:
        A function that represents the analyst node.
    """
    sys_msg = load_system_prompt(agent_stack, "analyst")

    async def analyst_node(state: AgentState):
        # Filter messages to keep only recent relevant context (original task + last 20 messages)
        # Analyst may need more context for code analysis
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=20)
        current_messages = [SystemMessage(content=sys_msg)] + filtered_messages

        # We allow the analyst more freedom ("auto") since they often need to chat
        # to think. But in the end they should use finish_task.
        chain = llm.bind_tools(tools, tool_choice="auto")

        response = await chain.ainvoke(current_messages)
        response = sanitize_response(response)

        has_content = bool(response.content)
        has_tool_calls = bool(getattr(response, "tool_calls", []))

        if has_content or has_tool_calls:
            log_agent_response("analyst", response)

        recorded, agent_summary = record_finish_task_summary(state, "analyst", response)
        result: dict[str, Any] = {"messages": [response], "current_node": "analyst"}
        if recorded:
            result["agent_summary"] = agent_summary
        return result

    return analyst_node
