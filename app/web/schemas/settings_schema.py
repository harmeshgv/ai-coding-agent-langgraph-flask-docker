"""Pydantic schemas for settings form validation.

These schemas define the structure and validation rules for data flowing
between the web layer (forms) and the service layer.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TrelloConfigSchema(BaseModel):
    """Schema for Trello configuration form data."""

    api_key: Optional[str] = Field(default=None, description="Trello API key")
    api_token: Optional[str] = Field(default=None, description="Trello API token")
    base_url: str = Field(
        default="https://api.trello.com/1", description="Trello API base URL"
    )
    board_id: Optional[str] = Field(default=None, description="Trello board ID")
    backlog_list: Optional[str] = Field(
        default=None, description="List ID for backlog tasks"
    )
    readfrom_list: Optional[str] = Field(
        default=None, description="List ID to read tasks from"
    )
    progress_list: Optional[str] = Field(
        default=None, description="List ID for in-progress tasks"
    )
    moveto_list: Optional[str] = Field(
        default=None, description="List ID to move completed tasks to"
    )

    @field_validator("api_key", "api_token", "board_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None."""
        if v == "":
            return None
        return v


class GitHubConfigSchema(BaseModel):
    """Schema for GitHub Projects configuration form data."""

    base_url: str = Field(
        default="https://api.github.com", description="GitHub API base URL"
    )
    api_token: Optional[str] = Field(
        default=None,
        description="GitHub PAT for board operations (falls back to GITHUB_TOKEN env)",
    )
    project_owner: Optional[str] = Field(
        default=None, description="GitHub project owner (user or organization)"
    )
    project_number: Optional[int] = Field(
        default=None, description="GitHub project number"
    )
    board_id: Optional[str] = Field(
        default=None, description="GitHub project node ID (fetched automatically)"
    )
    backlog_list: Optional[str] = Field(
        default=None, description="Column name for backlog tasks"
    )
    readfrom_list: Optional[str] = Field(
        default=None, description="Column name to read tasks from"
    )
    progress_list: Optional[str] = Field(
        default=None, description="Column name for in-progress tasks"
    )
    moveto_list: Optional[str] = Field(
        default=None, description="Column name to move completed tasks to"
    )

    @field_validator("project_owner", "board_id", "api_token", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None."""
        if v == "":
            return None
        return v

    @field_validator("project_number", mode="before")
    @classmethod
    def empty_str_to_none_int(cls, v) -> Optional[int]:
        """Convert empty strings to None, parse int."""
        if v == "" or v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class JiraConfigSchema(BaseModel):
    """Schema for Jira configuration form data."""

    username: Optional[str] = Field(default=None, description="Jira username")
    api_token: Optional[str] = Field(default=None, description="Jira API token")
    jql_query: Optional[str] = Field(default=None, description="JQL query for tasks")

    @field_validator("username", "api_token", "jql_query", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None."""
        if v == "":
            return None
        return v


class LLMConfigSchema(BaseModel):
    """Schema for LLM configuration form data."""

    provider: str = Field(default="mistral", description="LLM provider name")
    model_large: Optional[str] = Field(default=None, description="Large model name")
    model_small: Optional[str] = Field(default=None, description="Small model name")
    temperature: Optional[str] = Field(default=None, description="LLM temperature")

    @field_validator("provider", mode="before")
    @classmethod
    def default_provider(cls, v: Optional[str]) -> str:
        """Default to mistral if empty."""
        if not v or v == "":
            return "mistral"
        return v

    @field_validator("model_large", "model_small", "temperature", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None."""
        if v == "":
            return None
        return v


class SettingsFormSchema(BaseModel):
    """Schema for the complete settings form submission."""

    task_system_type: str = Field(default="TRELLO", description="Task system type")
    agent_skill_level: Optional[str] = Field(
        default=None, description="Agent skill level"
    )
    polling_interval_seconds: int = Field(
        default=60, ge=10, le=3600, description="Polling interval in seconds"
    )
    repo_type: str = Field(default="GITHUB", description="Repository type")
    github_repo_url: Optional[str] = Field(
        default=None, description="GitHub repository URL"
    )
    is_active: bool = Field(default=False, description="Whether agent is active")

    trello_config: Optional[TrelloConfigSchema] = Field(
        default=None, description="Trello configuration"
    )
    github_config: Optional[GitHubConfigSchema] = Field(
        default=None, description="GitHub Projects configuration"
    )
    jira_config: Optional[JiraConfigSchema] = Field(
        default=None, description="Jira configuration"
    )
    llm_config: LLMConfigSchema = Field(
        default_factory=LLMConfigSchema, description="LLM configuration"
    )

    @field_validator("task_system_type", mode="before")
    @classmethod
    def default_task_system(cls, v: Optional[str]) -> str:
        """Default to TRELLO if empty."""
        if not v or v == "":
            return "TRELLO"
        return v

    @field_validator("polling_interval_seconds", mode="before")
    @classmethod
    def parse_polling_interval(cls, v) -> int:
        """Parse polling interval, defaulting to 60 on error."""
        if v is None or v == "":
            return 60
        try:
            return int(v)
        except (ValueError, TypeError):
            return 60

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_is_active(cls, v) -> bool:
        """Parse is_active from form checkbox."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "on", "yes")
        return bool(v)
