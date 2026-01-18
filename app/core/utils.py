"""Utility functions for the application."""

import logging
import os

from cryptography.fernet import Fernet


def setup_logging():
    """Setup logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
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


def log_and_validate_env(logger):
    """check and log Env Vars and return encryption key."""
    keys_to_log = [
        "GOOGLE_API_KEY",
        "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_API_KEY",
    ]

    for env_name in keys_to_log:
        value = os.environ.get(env_name, "")
        if value:
            logger.info("%s: %s", env_name, mask_secret(value))
        else:
            logger.info("%s is not set", env_name)

    logger.info("OLLAMA_BASE_URL: %s", os.environ.get("OLLAMA_BASE_URL", "Not set"))

    ENABLE_MCP_SERVERS = os.environ.get("ENABLE_MCP_SERVERS", "true").lower() not in {
        "false",
        "0",
        "no",
    }
    logger.info("MCP enabled: %s", ENABLE_MCP_SERVERS)
    logger.info("DATABASE_DIR: %s", os.environ.get("DATABASE_DIR", "Not set"))
    logger.info("WORKBENCH: %s", os.environ.get("WORKBENCH", "Not set"))
    logger.info("WORKSPACE: %s", os.environ.get("WORKSPACE", "Not set"))

    # Kritische Checks
    if not os.environ.get("GITHUB_TOKEN"):
        raise ValueError("GITHUB_TOKEN is not set.")

    if not os.environ.get("WORKSPACE"):
        raise ValueError("WORKSPACE is not set.")

    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise ValueError("ENCRYPTION_KEY is not set. Application cannot start.")
    encryption_key = Fernet(key.encode())

    return encryption_key
