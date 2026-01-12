"""Initializes and exports Flask extension objects.

This module creates instances of Flask extensions (like SQLAlchemy and APScheduler)
in a central location. These instances can then be imported by other parts of
the application and initialized in the app factory (`create_app`) without
causing circular import issues.

By creating extension objects here (e.g., `db`, `scheduler`) but not yet
binding them to a specific Flask app, we can avoid circular import issues.

For example, the main app file (main.py) and the models file (models.py) both
need to import the `db` object. If `db` were created in `main.py`, `models.py`
couldn't import it without creating a circular dependency.
"""

from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
scheduler = APScheduler()
