"""A collection of tools for the agent to interact with the implementation plan"""

import logging

from langchain_core.tools import tool

from app.agent.utils import write_to_file_in_workspace

logger = logging.getLogger(__name__)


@tool
def write_plan(content: str):
    """
    Writes the implementation plan to a file.
    """
    return write_to_file_in_workspace("plan.md", content)
