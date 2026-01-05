import logging

from agent.state import AgentState
from agent.utils import (
    filter_messages_for_llm,
    load_system_prompt,
    log_agent_response,
    sanitize_response,
)
from langchain.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)


def create_analyst_node(llm: BaseChatModel, tools, repo_url, agent_stack):
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
            log_agent_response(logger, "analyst", response)

        return {"messages": [response]}

    return analyst_node
