"""Defines the SQLAlchemy database models for the application.

This module contains the class definitions for all database models used by
SQLAlchemy. Each class corresponds to a table in the database.
"""

import os
from typing import Any, Dict

from cryptography.fernet import Fernet
from sqlalchemy import ForeignKey, LargeBinary, TypeDecorator

from app.core.extensions import db

key = os.environ.get("ENCRYPTION_KEY")
if not key:
    raise ValueError("ENCRYPTION_KEY is not set. Application cannot start.")
encryption_key = Fernet(key.encode())


# pylint: disable=too-many-ancestors
class EncryptedString(TypeDecorator):
    """Encrypts strings on write and decrypts on read."""

    impl = LargeBinary
    cache_ok = True

    @property
    def python_type(self):
        """Return the Python type for this custom type."""
        return str

    def process_bind_param(self, value, dialect):  # pylint: disable=unused-argument
        """Encrypt before saving."""
        if value is None:
            return value

        if not isinstance(value, str):
            raise TypeError("EncryptedString only supports string values.")

        value_bytes = value.encode("utf-8")
        return encryption_key.encrypt(value_bytes)

    def process_result_value(self, value, dialect):  # pylint: disable=unused-argument
        """Decrypt after loading."""
        if value is None:
            return value

        # Handle backward compatibility: if value is already a string (unencrypted),
        # return it as-is. This allows migration from unencrypted to encrypted data.
        if isinstance(value, str):
            return value

        try:
            decrypted_value = encryption_key.decrypt(value)
            return decrypted_value.decode("utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            # If decryption fails, assume it's legacy unencrypted data
            # Try to decode as UTF-8 string
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)

    def process_literal_param(self, value, dialect):
        """Handles rendering of a literal parameter for this type.

        This is used for features like literal_binds.
        """
        processed_value = self.process_bind_param(value, dialect)
        if processed_value is None:
            return "NULL"

        return dialect.type_descriptor(self.impl).process_literal_param(  # type: ignore[attr-defined] # pylint: disable=line-too-long
            processed_value, dialect
        )


# pylint: disable=too-few-public-methods
DEFAULT_TRELLO_BASE_URL = "https://api.trello.com/1"


class AgentConfig(db.Model):
    """Represents the configuration for the AI agent.

    This model stores settings required for the agent to operate, including
    connections to task management systems (like Trello), version control
    repositories (like GitHub), and its own operational parameters like
    polling frequency.
    """

    __tablename__ = "agent_config"

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
    github_repo_url = db.Column(
        db.String(200),
        default="https://github.com/tomwey2/calculator-spring-docker-jenkins.git",
    )
    polling_interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    agent_skill_level = db.Column(db.String(50), nullable=True)
    task_systems = db.relationship(
        "TaskSystem",
        back_populates="agent_config",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def get_task_system(self, provider: str) -> "TaskSystem | None":
        """Get TaskSystem by provider name."""
        for ts in self.task_systems:
            if ts.board_provider == provider:
                return ts
        return None

    def get_active_task_system(self) -> "TaskSystem | None":
        """Get the currently active TaskSystem based on task_system_type."""
        provider = "trello" if self.task_system_type == "TRELLO" else self.task_system_type.lower()
        return self.get_task_system(provider)

    def __repr__(self):
        return f"<AgentConfig {self.id} type={self.task_system_type}>"

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
    agent_config_id = db.Column(
        db.Integer,
        ForeignKey("agent_config.id"),
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
    backlog_state = db.Column(db.String(100), nullable=True)
    readfrom_state = db.Column(db.String(100), nullable=True)
    in_progress_state = db.Column(db.String(100), nullable=True)
    moveto_state = db.Column(db.String(100), nullable=True)

    agent_config = db.relationship(
        "AgentConfig",
        back_populates="task_systems",
    )

    __table_args__ = (
        db.UniqueConstraint('agent_config_id', 'board_provider', name='uq_agent_config_provider'),
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
    branch_name = db.Column(db.String(200), nullable=False)
    repo_url = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"<Task id={self.task_id} branch={self.branch_name}>"
