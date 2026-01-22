"""
Defines the router node for the agent graph.

This node is responsible for the initial analysis of a task. It uses a
specialized LLM call to classify the user's request and decide which
specialist agent (e.g., Coder, Bugfixer, Analyst) should handle it next.
"""

import logging
from typing import Dict, Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.services.message_processing import filter_messages_for_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You are the Senior Technical Lead.
Your job is to analyze the incoming task and route it to the correct specialist.

OPTIONS:
1. 'coder': For implementing new features, creating new files, or refactoring.
2. 'bugfixer': For fixing errors, debugging, or solving issues in existing code.
3. 'analyst': For explaining code, reviewing architecture, or answering questions (NO code changes).

Respond ONLY with valid JSON that matches {"role":"coder"|"bugfixer"|"analyst"} with no additional text or markdown.
"""


# pylint: disable=too-few-public-methods
class RouterDecision(BaseModel):
    """Classify the incoming task into the correct category."""

    role: Literal["coder", "bugfixer", "analyst"] = Field(
        ..., description="The specific role needed to solve the task."
    )


def create_router_node(llm):
    """
    Factory function that creates the router node for the agent graph.

    Args:
        llm: The language model to be used for routing decisions.

    Returns:
        A function that represents the router node.
    """
    structured_llm = llm.with_structured_output(RouterDecision, method="json_mode")

    async def router_node(state: AgentState) -> Dict[str, str]:
        # Router only needs the original task to make routing decision
        filtered_messages = filter_messages_for_llm(state["messages"], max_messages=3)
        base_messages = [SystemMessage(content=ROUTER_SYSTEM)] + filtered_messages
        current_messages = list(base_messages)

        for attempt in range(3):
            try:
                response = await structured_llm.ainvoke(current_messages)
                logger.info("Router decided: %s", response.role)
                return {"next_step": response.role, "current_node": "router"}
            except OutputParserException as exc:
                logger.warning(
                    "Router invalid JSON attempt %d/3: %s",
                    attempt + 1,
                    exc,
                    exc_info=True,
                )
                correction = HumanMessage(
                    content=(
                        "STOP. Respond ONLY with compact JSON like "
                        '{"role":"coder"} and no other text.'
                    )
                )
                current_messages.append(correction)

        logger.error("Router failed to produce valid JSON after retries.")
        raise RuntimeError("Router failed to produce valid JSON after 3 retries.")

    return router_node
