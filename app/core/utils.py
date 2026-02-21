"""Utility functions for the application."""

import json
import logging
import logging.config
import os
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet

from app.core.environment_settings import EnvironmentSettings


def setup_logging(
    config_file_path: Path | None = None,
) -> logging.Logger:
    """
    Setup logging for the application.
    
    This function configures logging for the application. It can load a configuration
    from a json or ini style file if provided, or use a default configuration.
    """

    logger = logging.getLogger("entrypoint")

    config_path: Path | None = config_file_path
    if config_path is None:
        env_config = os.environ.get("LOGGING_CONFIG_FILE")
        if env_config:
            config_path = Path(env_config)

    if config_path:
        if config_path.exists():
            suffix = config_path.suffix.lower()
            if suffix == ".json":
                with config_path.open("r", encoding="utf-8") as config_file_handle:
                    config_data: Dict[str, Any] = json.load(config_file_handle)
                config_data.setdefault("disable_existing_loggers", False)
                _ensure_log_handler_directories(config_data)
                logging.config.dictConfig(config_data)
            else:
                logging.config.fileConfig(config_path, disable_existing_loggers=False)
            return logger
        logger.warning(
            "Logging config file '%s' not found. Falling back to built-in defaults.",
            config_path,
        )

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(name)s - %(levelname)s - %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "standard",
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console"],
        },
        "loggers": {
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "werkzeug": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(logging_config)
    return logger


def _ensure_log_handler_directories(config_data: Dict[str, Any]) -> None:
    """Create directories required by file-based log handlers."""

    handlers = config_data.get("handlers", {})
    for handler_name, handler_config in handlers.items():
        filename = handler_config.get("filename")
        if not filename:
            continue
        path = Path(filename).expanduser()
        parent = path.parent
        if parent.exists() or str(parent) == ".":
            continue
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logging.getLogger("entrypoint").warning(
                "Failed to create log directory for handler '%s': %s",
                handler_name,
                error,
            )


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
    logger.info("LLM_CALLS_PER_SECOND: %s", env_settings.llm_calls_per_second)

    encryption_key = Fernet(env_settings.encryption_key.encode())

    return encryption_key
