"""Pytest fixtures and path setup for agent tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Set up minimal required environment variables before any imports
# Only ENCRYPTION_KEY and WORKSPACE are required at startup
if "ENCRYPTION_KEY" not in os.environ:
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

if "WORKSPACE" not in os.environ:
    os.environ["WORKSPACE"] = str(PROJECT_ROOT / "workspace")

# GITHUB_TOKEN is now optional - tests that need it will set it explicitly

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def setup_test_env_settings():
    """Set up test environment settings before each test.
    
    This fixture runs automatically before each test and ensures
    that environment settings are properly initialized for testing.
    
    IMPORTANT: Tests that use monkeypatch.setenv() or patch.dict(os.environ)
    MUST call set_env_settings(None) after changing environment variables
    to force settings to reload from the new environment.
    
    Note: GITHUB_TOKEN is now optional. Tests that need GitHub
    functionality should set it explicitly.
    """
    from app.core.config import set_env_settings
    
    # Reset settings before each test to ensure clean state
    set_env_settings(None)
    
    yield
    
    # Reset after test to ensure next test starts fresh
    set_env_settings(None)


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    from flask import Flask
    from app.core.extensions import db
    
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db_session(app):
    """Create a database session for testing."""
    from app.core.extensions import db
    
    with app.app_context():
        yield db.session
