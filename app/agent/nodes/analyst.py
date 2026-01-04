import logging

from agent.state import AgentState
from agent.utils import load_system_prompt, sanitize_response, filter_messages_for_llm
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
        logger.info(
            f"\n=== ANALYST RESPONSE ===\nContent: '{response.content}'\nTool Calls: {response.tool_calls}\n============================"
        )

        return {"messages": [response]}

    return analyst_node
