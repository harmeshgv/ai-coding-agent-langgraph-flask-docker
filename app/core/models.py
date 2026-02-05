"""Defines the SQLAlchemy database models for the application.

This module contains the class definitions for all database models used by
SQLAlchemy. Each class corresponds to a table in the database.
"""

from typing import Any, Dict

from sqlalchemy import ForeignKey

from app.core.extensions import db
from app.core.security import EncryptedString

# pylint: disable=too-few-public-methods
DEFAULT_TRELLO_BASE_URL = "https://api.trello.com/1"


class AgentSettings(db.Model):
    """Represents the configuration for the AI agent.

    This model stores settings required for the agent to operate, including
    connections to task management systems (like Trello), version control
    repositories (like GitHub), and its own operational parameters like
    polling frequency.
    """

    __tablename__ = "agent_settings"

    id = db.Column(db.Integer, primary_key=True)
    # Generic Task System Fields
    task_system_type = db.Column(
        db.String(50), nullable=False, default="TRELLO"
    )  # e.g., "TRELLO", "JIRA", "CUSTOM"

    task_backlog_state = db.Column(db.String(100), nullable=True)
    task_readfrom_state = db.Column(db.String(100), nullable=True)
    task_in_progress_state = db.Column(db.String(100), nullable=True)
    task_moveto_state = db.Column(db.String(100), nullable=True)
    llm_provider = db.Column(db.String(50), nullable=True)
    llm_model_large = db.Column(db.String(100), nullable=True)
    llm_model_small = db.Column(db.String(100), nullable=True)
    llm_temperature = db.Column(db.String(16), nullable=True)

    # Existing Fields
    repo_type = db.Column(
        db.String(50), nullable=False, default="GITHUB"
    )  # e.g., "GITHUB", "BITBUCKET"
    github_repo_url = db.Column(db.String(200))
    polling_interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    agent_skill_level = db.Column(db.String(50), nullable=True)
    task_systems = db.relationship(
        "TaskSystem",
        back_populates="agent_settings",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def get_task_system(self, provider: str) -> "TaskSystem | None":
        """Get TaskSystem by provider name."""
        if self.task_systems and isinstance(self.task_systems, list):
            for ts in self.task_systems:
                if ts.board_provider == provider:
                    return ts
        return None

    def get_active_task_system(self) -> "TaskSystem | None":
        """Get the currently active TaskSystem based on task_system_type."""
        provider = "trello" if self.task_system_type == "TRELLO" else self.task_system_type.lower()
        return self.get_task_system(provider)

    def __repr__(self):
        return f"<AgentSettings {self.id} type={self.task_system_type}>"

    def as_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary of column values for logging/debugging."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns  # type: ignore[attr-defined]
        }


class TaskSystem(db.Model):
    """Represents an external task system configuration (e.g., Trello, GitHub Projects)."""

    __tablename__ = "task_system"

    id = db.Column(db.Integer, primary_key=True)
    agent_settings_id = db.Column(
        db.Integer,
        ForeignKey("agent_settings.id"),
        nullable=False,
        index=True,
    )
    task_system_type = db.Column(db.String(50), nullable=False, default="TRELLO")
    board_provider = db.Column(db.String(50), nullable=False)
    api_key = db.Column(EncryptedString, nullable=True)
    token = db.Column(EncryptedString, nullable=True)
    base_url = db.Column(db.String(200), nullable=True)
    board_id = db.Column(db.String(100), nullable=True)
    # GitHub Projects specific fields
    project_owner = db.Column(db.String(100), nullable=True)
    project_number = db.Column(db.Integer, nullable=True)
    # State mappings per provider
    state_backlog = db.Column(db.String(100), nullable=True)
    state_todo = db.Column(db.String(100), nullable=True)
    state_in_progress = db.Column(db.String(100), nullable=True)
    state_in_review = db.Column(db.String(100), nullable=True)

    agent_settings = db.relationship(
        "AgentSettings",
        back_populates="task_systems",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "agent_settings_id", "board_provider", name="uq_agent_settings_provider"
        ),
    )

    def __repr__(self):
        return f"<TaskSystem {self.id} provider={self.board_provider}>"


# pylint: disable=too-few-public-methods
class Task(db.Model):
    """Model for tracking tasks"""

    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    task_name = db.Column(db.String(500), nullable=False)
    branch_name = db.Column(db.String(200), nullable=True)
    repo_url = db.Column(db.String(200), nullable=True)
    pr_number = db.Column(db.Integer, nullable=True)
    pr_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self):
        return f"<Task id={self.task_id} branch={self.branch_name}>"
