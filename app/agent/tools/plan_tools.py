"""A collection of tools for the agent to interact with the implementation plan"""

import logging

from langchain_core.tools import tool

from app.core.plan_utils import save_plan_to_db

logger = logging.getLogger(__name__)


@tool
def write_plan(content: str):
    """
    Writes the implementation plan to a file.
    """
    if not save_plan_to_db(content):
        return "No task in database found. Can not store the plan."
    return "Successfully wrote plan to database"
