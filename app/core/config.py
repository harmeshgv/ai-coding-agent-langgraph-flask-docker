"""Flask application configuration.

This module defines the configuration variables for the Flask application.
It follows a common pattern of sourcing values from environment variables
for production-readiness, while providing sensible defaults for local
development.

Attributes:
    SECRET_KEY (str): A secret key for signing session cookies.
    SQLALCHEMY_DATABASE_URI (str): The connection URI for the database.
    SQLALCHEMY_TRACK_MODIFICATIONS (bool): Disables a SQLAlchemy feature.
    SCHEDULER_API_ENABLED (bool): Enables the built-in scheduler API.
"""

import os
from pathlib import Path

# Best practice: Load secrets from environment variables
# For simplicity in this phase, we use a default secret key.
SECRET_KEY = os.environ.get("SECRET_KEY", "a-default-secret-key-for-development")

# Database configuration
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = Path(os.environ.get("DATABASE_DIR", BASE_DIR / "instance"))
SQLALCHEMY_DATABASE_URI = (
    os.environ.get("DATABASE_URL") or f"sqlite:///{DATABASE_DIR / 'agent.db'}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Scheduler configuration
SCHEDULER_API_ENABLED = True
