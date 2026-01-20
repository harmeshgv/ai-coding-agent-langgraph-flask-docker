"""Defines the SQLAlchemy database models for the application.

This module contains the class definitions for all database models used by
SQLAlchemy. Each class corresponds to a table in the database.
"""

import json
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
class EncryptedDict(TypeDecorator):
    """Encrypts dictionaries on write and returns dicts on read."""

    impl = LargeBinary  # Stored as Binary/Blob in the DB
    cache_ok = True

    @property
    def python_type(self):
        return dict

    def process_bind_param(self, value, dialect):
        """Encrypt before saving."""
        if value is None:
            return value

        if not isinstance(value, dict):
            raise TypeError("EncryptedDict only supports dictionary values.")

        value_bytes = json.dumps(value).encode("utf-8")
        return encryption_key.encrypt(value_bytes)

    def process_result_value(self, value, dialect):
        """Decrypt after loading."""
        if value is None:
            return value

        decrypted_value = encryption_key.decrypt(value)
        decoded_value = decrypted_value.decode("utf-8")

        try:
            loaded_value = json.loads(decoded_value or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Stored EncryptedDict value is not valid JSON") from exc

        if not isinstance(loaded_value, dict):
            raise ValueError("Stored EncryptedDict value did not decode to a dict")

        return loaded_value

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
    task_system_id = db.Column(
        db.Integer,
        ForeignKey("task_system.id"),
        nullable=True,
        unique=True,
        index=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    task_system = db.relationship(
        "TaskSystem",
        back_populates="agent_config",
        uselist=False,
    )

    def __repr__(self):
        return f"<AgentConfig {self.id} task_system_id={self.task_system_id}>"

    def as_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary of column values for logging/debugging."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns  # type: ignore[attr-defined]
        }


class TaskSystem(db.Model):
    """Represents an external task system configuration (e.g., Trello)."""

    __tablename__ = "task_system"

    id = db.Column(db.Integer, primary_key=True)
    task_system_type = db.Column(db.String(50), nullable=False, default="TRELLO")
    board_provider = db.Column(db.String(50), nullable=False)
    api_key = db.Column(db.String(200), nullable=True) # encrypt later
    token = db.Column(db.String(200), nullable=True) # encrypt later
    base_url = db.Column(db.String(200), nullable=True)
    board_id = db.Column(db.String(100), nullable=True)

    agent_config = db.relationship(
        "AgentConfig",
        back_populates="task_system",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self):
        return f"<TaskSystem {self.id} type={self.task_system_type}>"

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Task id={self.task_id} branch={self.branch_name}>"
