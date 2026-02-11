"""
Database repository functions for managing tasks and their corresponding branches.
"""

from typing import Any
import logging
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.localdb.models import Task

logger = logging.getLogger(__name__)


def read_db_task(id: int | None = None, task_id: str | None = None) -> Task | None:  # pylint: disable=redefined-builtin
    """Load the saved task from the database."""
    logger.debug("Reading task from database with id: %s, task_id: %s", id, task_id)
    task = None
    if id is not None:
        task = db.session.get(Task, id)

    # Priority 2: search by task_id
    elif task_id is not None:
        stmt = select(Task).where(Task.task_id == task_id)
        task = db.session.execute(stmt).scalar_one_or_none()

    # Priority 3 (Fallback): get the first task
    # We sort by ID, so "the first" is uniquely defined.
    else:
        stmt = select(Task).order_by(Task.id.asc()).limit(1)
        task = db.session.execute(stmt).scalar_one_or_none()

    if task is None:
        logger.warning("No task found in database")
    else:
        logger.info("Current task found: %s (%s)", task.task_id, task.task_name)
    return task


def create_db_task(task_id: str, task_name: str) -> Task:
    """insert task into sqlalchemy database"""
    logger.debug("Creating task in database: %s (%s)", task_id, task_name)
    try:
        new_task = Task(task_id=task_id, task_name=task_name)
        db.session.add(new_task)
        db.session.commit()
        return new_task

    except IntegrityError as e:
        # Happens if task_id (unique=True) is already assigned
        db.session.rollback()
        logging.error("Error creating task: %s", e)
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error("Error creating task: %s", e)
        return None


def update_db_task(task_id: str, **kwargs: Any) -> Task | None:
    """
    Updates any fields of a task.
    Call e.g.: update_task(1, task_name="New", status="Done", priority=5)
    """
    task = read_db_task(task_id=task_id)

    if not task:
        return None

    # Iteriere über alle übergebenen Argumente
    for key, value in kwargs.items():
        # Sicherheits-Check: Hat das Model dieses Attribut überhaupt?
        if hasattr(task, key):
            # Verhindern, dass man aus Versehen die ID ändert (optional, aber empfohlen)
            if key == "id":
                continue

            # Setzt den Wert dynamisch: task.key = value
            setattr(task, key, value)
        else:
            logging.warning("Attribute '%s' does not exist in Task model and will be ignored.", key)

    try:
        logger.debug(
            "Updating task %d (%s) in database with values: %s", task.id, task.task_id, kwargs
        )
        db.session.commit()
        return task
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error("Error updating task: %s", e)
        return None


def delete_db_task(task_id: str) -> bool:
    """
    Removes the task mapping from the database.
    Returns True if a record was deleted, False otherwise.
    """
    task = read_db_task(task_id=task_id)

    if task:
        logger.debug("Deleting task from database: %s", task_id)
        db.session.delete(task)
        db.session.commit()
        return True

    return False
