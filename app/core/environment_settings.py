"""Centralized environment settings for the application.

This module provides a single dataclass that accumulates all environment
variables used throughout the application. All other modules should import
from here instead of accessing os.environ directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvironmentSettings:  # pylint: disable=too-many-instance-attributes
    """Accumulates all environment variables used in the application.

    This dataclass centralizes environment variable access, making the code
    more testable and easier to reason about. Use the from_env() factory
    method to create an instance from the current environment.

    Most settings are optional and validated at use time via helper methods
    like require_github_token() or require_llm_api_key(). This allows tests
    and features that don't need certain credentials to run without them.

    Attributes:
        encryption_key: Fernet encryption key for database encryption (required).
        workspace: Path to the coding workspace (required).
        github_token: GitHub Personal Access Token for API access (optional).
        openai_api_key: OpenAI API key for LLM access (optional).
        mistral_api_key: Mistral AI API key for LLM access (optional).
        google_api_key: Google AI/Gemini API key for LLM access (optional).
        openrouter_api_key: OpenRouter API key for LLM access (optional).
        anthropic_api_key: Anthropic Claude API key for LLM access (optional).
        ollama_api_key: Ollama API key (optional).
        ollama_base_url: Base URL for Ollama server.
        secret_key: Flask secret key for session management.
        database_url: Database connection URL (optional, uses sqlite default).
        instance_dir: Directory for sqlite database files and other instance data.
        workbench: Docker container name for the workbench.
        agent_stack: Preferred agent stack (backend/frontend) override.
        github_repo_url: Default GitHub repository URL.
        enable_mcp_servers: Whether to enable MCP servers.
    """

    # Required settings (needed for app startup)
    encryption_key: str
    workspace: str

    # GitHub integration (optional, validated at use time)
    github_token: str | None = None

    # LLM API Keys (all optional, validated at use time)
    openai_api_key: str | None = None
    mistral_api_key: str | None = None
    google_api_key: str | None = None
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_api_key: str | None = None

    # Configuration with defaults
    ollama_base_url: str = "http://host.docker.internal:11434"
    secret_key: str = "a-default-secret-key-for-development"
    database_url: str | None = None
    instance_dir: str = "/coding-agent/app/instance"
    workbench: str = ""
    agent_stack: str = ""
    github_repo_url: str = ""
    enable_mcp_servers: bool = True
    llm_calls_per_second: float = 0.0

    @classmethod
    def from_env(cls) -> EnvironmentSettings:
        """Create EnvironmentSettings from the current environment.

        Only ENCRYPTION_KEY and WORKSPACE are required at initialization.
        Other settings like GITHUB_TOKEN are optional and validated when used.

        Raises:
            ValueError: If required environment variables (ENCRYPTION_KEY, WORKSPACE) are missing.

        Returns:
            EnvironmentSettings instance populated from os.environ.
        """
        # Required variables - raise if missing
        encryption_key = os.environ.get("ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("ENCRYPTION_KEY is not set. Application cannot start.")

        workspace = os.environ.get("WORKSPACE")
        if not workspace:
            raise ValueError("WORKSPACE is not set.")

        # Parse ENABLE_MCP_SERVERS boolean
        enable_mcp_str = os.environ.get("ENABLE_MCP_SERVERS", "true").lower()
        enable_mcp_servers = enable_mcp_str in {"true", "1", "yes", "on"}

        llm_calls_per_second = float(os.environ.get("LLM_CALLS_PER_SECOND", "0"))

        return cls(
            encryption_key=encryption_key,
            workspace=workspace,
            github_token=os.environ.get("GITHUB_TOKEN"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            mistral_api_key=os.environ.get("MISTRAL_API_KEY"),
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            ollama_api_key=os.environ.get("OLLAMA_API_KEY"),
            ollama_base_url=os.environ.get(
                "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
            ),
            secret_key=os.environ.get("SECRET_KEY", "a-default-secret-key-for-development"),
            database_url=os.environ.get("DATABASE_URL"),
            instance_dir=os.environ.get("INSTANCE_DIR", "/coding-agent/app/instance"),
            workbench=os.environ.get("WORKBENCH", "workbench-backend"),
            agent_stack=os.environ.get("AGENT_STACK", ""),
            github_repo_url=os.environ.get("GITHUB_REPO_URL", ""),
            enable_mcp_servers=enable_mcp_servers,
            llm_calls_per_second=llm_calls_per_second,
        )

    def get_database_uri(self, base_dir: Path) -> str:
        """Get the database URI, computing default if not set.

        Args:
            base_dir: Base directory for computing default sqlite path.

        Returns:
            Database connection URI string.
        """
        if self.database_url:
            return self.database_url

        db_dir = Path(self.instance_dir) if self.instance_dir else base_dir / "instance"
        db_dir = db_dir.resolve()
        return f"sqlite:///{db_dir / 'agent.db'}"

    def require_github_token(self) -> str:
        """Get GitHub token or raise if not configured.

        Use this method when GitHub functionality is required. This allows
        tests and features that don't use GitHub to run without a token.

        Returns:
            GitHub token string.

        Raises:
            ValueError: If GITHUB_TOKEN is not set with helpful context.
        """
        if not self.github_token:
            raise ValueError(
                "GITHUB_TOKEN is required for this operation. "
                "Set the GITHUB_TOKEN environment variable or configure it in settings."
            )
        return self.github_token

    def require_encryption_key(self) -> str:
        """Get encryption key or raise if not configured.

        Returns:
            Encryption key string.

        Raises:
            ValueError: If ENCRYPTION_KEY is not set.
        """
        if not self.encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY is required. "
                "Set the ENCRYPTION_KEY environment variable."
            )
        return self.encryption_key

    def require_llm_api_key(self, provider: str) -> str:
        """Get LLM API key for a specific provider or raise if not configured.

        Args:
            provider: LLM provider name (e.g., "openai", "mistral", "google").

        Returns:
            API key string for the specified provider.

        Raises:
            ValueError: If the API key for the provider is not set.
        """
        provider_lower = provider.lower()

        # Mapping of provider to (api_key, env_var_name, is_optional)
        key_mapping = {
            "openai": (self.openai_api_key, "OPENAI_API_KEY", False),
            "mistral": (self.mistral_api_key, "MISTRAL_API_KEY", False),
            "google": (self.google_api_key, "GOOGLE_API_KEY", False),
            "openrouter": (self.openrouter_api_key, "OPENROUTER_API_KEY", False),
            "anthropic": (self.anthropic_api_key, "ANTHROPIC_API_KEY", False),
            "ollama": (self.ollama_api_key, "OLLAMA_API_KEY", True),
        }

        if provider_lower not in key_mapping:
            raise ValueError(f"Unknown LLM provider: {provider}")

        api_key, env_var, is_optional = key_mapping[provider_lower]

        if not api_key and not is_optional:
            raise ValueError(
                f"{env_var} is required for {provider} LLM. "
                f"Set the {env_var} environment variable."
            )

        return api_key or ""

    def get_api_key(self, env_var_name: str) -> str:
        """Get an API key by its environment variable name.

        Args:
            env_var_name: Name of the environment variable (e.g., "OPENAI_API_KEY").

        Returns:
            The API key value or empty string if not set.

        Note:
            This method returns empty string for missing keys to maintain
            backward compatibility. Use require_llm_api_key() for strict validation.
        """
        key_map = {
            "OPENAI_API_KEY": self.openai_api_key,
            "MISTRAL_API_KEY": self.mistral_api_key,
            "GOOGLE_API_KEY": self.google_api_key,
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "OLLAMA_API_KEY": self.ollama_api_key,
        }

        return key_map.get(env_var_name) or ""
