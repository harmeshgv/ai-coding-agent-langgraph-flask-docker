"""Utility functions for the application."""

import logging

from cryptography.fernet import Fernet

from app.core.environment_settings import EnvironmentSettings


def setup_logging():
    """Setup logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return logging.getLogger("entrypoint")


def mask_secret(value: str) -> str:
    """Mask a secret value for logging."""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    head = value[:2]
    tail = value[-2:]
    return f"{head}{'*' * (len(value) - 4)}{tail}"


def log_and_validate_env(logger, env_settings: EnvironmentSettings):
    """Log environment variables and validate required settings, return encryption key.

    Note: GITHUB_TOKEN is now optional and validated at use time.
    Only ENCRYPTION_KEY and WORKSPACE are validated here.
    """
    keys_to_log = [
        ("GOOGLE_API_KEY", env_settings.google_api_key),
        ("MISTRAL_API_KEY", env_settings.mistral_api_key),
        ("OPENAI_API_KEY", env_settings.openai_api_key),
        ("OPENROUTER_API_KEY", env_settings.openrouter_api_key),
        ("ANTHROPIC_API_KEY", env_settings.anthropic_api_key),
        ("OLLAMA_API_KEY", env_settings.ollama_api_key),
    ]

    for env_name, value in keys_to_log:
        if value:
            logger.info("%s: %s", env_name, mask_secret(value))
        else:
            logger.info("%s is not set", env_name)

    logger.info("OLLAMA_BASE_URL: %s", env_settings.ollama_base_url)

    logger.info("MCP enabled: %s", env_settings.enable_mcp_servers)
    logger.info("INSTANCE_DIR: %s", env_settings.instance_dir or "Not set")
    logger.info("WORKBENCH: %s", env_settings.workbench or "Not set")
    logger.info("WORKSPACE: %s", env_settings.workspace)

    encryption_key = Fernet(env_settings.encryption_key.encode())

    return encryption_key
