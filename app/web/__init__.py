"""Flask application factory.

This module contains the `create_app` function that is responsible for
initializing the Flask application, configuring it, setting up extensions like
SQLAlchemy and APScheduler, and registering blueprints.
"""

import os

from core.extensions import db, scheduler
from cryptography.fernet import Fernet
from flask import Flask

from web.routes import web_bp


def create_app(encryption_key: Fernet) -> Flask:
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("core.config")
    app.config["FERNET_KEY"] = encryption_key

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)
    scheduler.init_app(app)

    # Das fügt alle Routen aus web_bp zur App hinzu
    app.register_blueprint(web_bp)
    return app
