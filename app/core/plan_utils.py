"""Service function for the plan."""

import logging
import os

from app.agent.utils import get_workspace
from app.core.localdb.db_task_utils import read_db_task, update_db_task

logger = logging.getLogger(__name__)


def save_plan_to_db(content: str) -> bool:
    task = read_db_task()
    if not task:
        return False
    update_db_task(task_id=task.task_id, plan_content=content)
    return True


def exist_plan() -> bool:
    """Check if the implementation plan exists in the database.

    Returns:
        True if implementation plan exists, False otherwise.
    """
    task = read_db_task()
    if not task:
        return False
    return bool(task.plan_content)


def get_plan() -> str:
    """Read and return the implementation plan from database.

    Returns:
        Content of implementation plan or a default message if not found.
    """
    task = read_db_task()
    if not task or not task.plan_content:
        return "No implementation plan found in database."
    return task.plan_content
