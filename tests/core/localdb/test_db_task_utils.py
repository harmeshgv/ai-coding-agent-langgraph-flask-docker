"""
Tests for the task repository.
"""

import pytest

from app.core.localdb.models import Task
from app.core.localdb.db_task_utils import (
    read_db_task,
    delete_db_task,
    create_db_task,
    update_db_task,
)


@pytest.fixture
def app_context(app):
    """Fixture to provide Flask app context."""
    with app.app_context():
        yield


def test_create_db_task_create_new(app_context, db_session):
    """Test creating a new task."""
    task = create_db_task(task_id="task123", task_name="Test Task")

    assert task.task_id == "task123"
    assert task.task_name == "Test Task"


def test_update_db_task_update_existing(app_context, db_session):
    """Test updating an existing task."""
    create_db_task(task_id="task123", task_name="Original Name")

    updated_task = update_db_task(
        task_id="task123", task_name="Updated Name", branch_name="feature/updated"
    )

    assert updated_task.task_name == "Updated Name"
    assert updated_task.branch_name == "feature/updated"

    all_tasks = Task.query.filter_by(task_id="task123").all()
    assert len(all_tasks) == 1


def test_get_task_by_id_exists(app_context, db_session):
    """Test getting a task by ID when it exists."""
    create_db_task(task_id="task123", task_name="Test Task")

    task = read_db_task(task_id="task123")
    assert task is not None
    assert task.task_id == "task123"
    assert task.task_name == "Test Task"


def test_get_task_by_id_not_exists(app_context, db_session):
    """Test getting a task by ID when it doesn't exist."""
    task = read_db_task(task_id="nonexistent")
    assert task is None


def test_remove_task_from_db_exists(app_context, db_session):
    """Test removing an existing task."""
    create_db_task(task_id="task123", task_name="Test Task")

    result = delete_db_task("task123")
    assert result is True

    task = read_db_task("task123")
    assert task is None


def test_remove_task_from_db_not_exists(app_context, db_session):
    """Test removing a non-existent task."""
    result = delete_db_task("nonexistent")
    assert result is False
