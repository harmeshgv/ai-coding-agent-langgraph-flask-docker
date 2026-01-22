"""
Defines the correction node for the agent graph.

This node is triggered when an agent produces a text response instead of the
expected tool call. It injects a new message into the state, instructing the
agent to correct its behavior and use a tool on the next attempt.
"""

import logging

from langchain_core.messages import HumanMessage

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_correction_node():
    """
    Factory function that creates the correction node for the agent graph.

    This node injects a corrective message into the state when an agent
    fails to call a tool.
    """

    async def correction_node(state: AgentState):  # pylint: disable=unused-argument
        logger.warning(
            "Agent generated text instead of tool call. Injecting correction message."
        )
        return {
            "messages": [
                HumanMessage(
                    content="ERROR: You responded with text but NO tool call. "
                    + "You MUST call a tool (e.g. thinking, write_to_file)."
                )
            ],
            "current_node": "correction",
        }

    return correction_node
