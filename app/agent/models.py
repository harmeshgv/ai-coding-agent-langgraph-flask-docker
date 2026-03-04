"""Data models for the agent."""

from dataclasses import dataclass


@dataclass
class AgentSummary:
    """Represents a summary entry from an agent role."""

    role: str
    summary: str

    def __post_init__(self):
        """Validate and normalize the fields."""
        if not isinstance(self.role, str):
            raise TypeError("role must be a string")
        if not isinstance(self.summary, str):
            raise TypeError("summary must be a string")

        self.role = self.role.strip()
        self.summary = self.summary.strip()

    def to_markdown(self) -> str:
        """Format the summary as a markdown entry with role prefix."""
        role_prefix = self.role.capitalize()
        return f"**[{role_prefix}]** {self.summary}"
