"""
Defines the Analyst agent node for the agent graph.

The Analyst is a specialist agent responsible for analyzing code, answering
questions about the codebase, and providing explanations without making
any modifications.
"""

import logging

from langchain.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from agent.state import AgentState
from agent.utils import (
    filter_messages_for_llm,
    load_system_prompt,
    log_agent_response,
    record_finish_task_summary,
    sanitize_response,
)

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

        # Wir erlauben dem Analysten etwas mehr Freiheit ("auto"), da er oft chatten muss,
        # um zu denken. Aber am Ende soll er finish_task nutzen.
        chain = llm.bind_tools(tools, tool_choice="auto")

        response = await chain.ainvoke(current_messages)
        response = sanitize_response(response)

        has_content = bool(response.content)
        has_tool_calls = bool(getattr(response, "tool_calls", []))

        if has_content or has_tool_calls:
            log_agent_response("analyst", response)

        recorded, agent_summary = record_finish_task_summary(state, "analyst", response)
        result = {"messages": [response]}
        if recorded:
            result["agent_summary"] = agent_summary
        return result

    return analyst_node
