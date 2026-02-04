"""Flask application configuration.

This module defines the configuration variables for the Flask application.
It uses EnvironmentSettings for centralized environment variable access.
"""

import logging
import threading
from pathlib import Path

from app.core.environment_settings import EnvironmentSettings

logger = logging.getLogger(__name__)

# Lazy initialization - settings loaded on first access
_ENV_SETTINGS: EnvironmentSettings | None = None
_settings_lock = threading.Lock()


def get_env_settings() -> EnvironmentSettings:
    """Get or initialize environment settings lazily.

    This function ensures settings are only loaded when first accessed,
    not at module import time. This allows tests to set up environment
    variables or inject mock settings before any code tries to access them.

    Thread-safe using double-check locking pattern.

    Returns:
        EnvironmentSettings instance populated from environment.
    """
    global _ENV_SETTINGS  # pylint: disable=global-statement
    if _ENV_SETTINGS is None:
        with _settings_lock:
            # Double-check pattern: another thread might have initialized
            # while we were waiting for the lock
            if _ENV_SETTINGS is None:
                _ENV_SETTINGS = EnvironmentSettings.from_env()
    return _ENV_SETTINGS


def set_env_settings(settings: EnvironmentSettings | None) -> None:
    """Override environment settings (primarily for testing).

    Args:
        settings: EnvironmentSettings instance to use, or None to reset.
    """
    global _ENV_SETTINGS  # pylint: disable=global-statement
    _ENV_SETTINGS = settings


# Database configuration
BASE_DIR = Path(__file__).resolve().parent.parent

# Note: Flask config values are NOT initialized here at module level.
# They will be set by the Flask app factory (create_app) which calls
# get_env_settings() after environment is properly set up.
# This allows tests to inject settings before Flask initialization.

SQLALCHEMY_TRACK_MODIFICATIONS = False
SCHEDULER_API_ENABLED = True
