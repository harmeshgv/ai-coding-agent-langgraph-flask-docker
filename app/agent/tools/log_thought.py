"""Tool for logging agent thoughts without affecting state."""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def log_thought(thought: str):
    """Log an internal thought to aid reasoning without changing state."""
    logger.debug("🤔 AGENT THOUGHT: %s", thought)
    return "Thought recorded. Proceed with the next tool."
