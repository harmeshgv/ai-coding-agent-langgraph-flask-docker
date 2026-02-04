from dotenv import load_dotenv

from app.core.config import get_env_settings
from app.core.extensions import db
from app.core.utils import log_and_validate_env, setup_logging

# Importe angepasst für Root-Level Execution
from app.web import create_app

load_dotenv()

if __name__ == "__main__":
    # 1. Logging Setup
    logger = setup_logging()
    logger.info("Starting Web Server...")

    # 2. Env Validierung
    encryption_key = log_and_validate_env(logger, get_env_settings())

    # 3. App erstellen
    app = create_app(encryption_key)

    # 4. DB Init (Macht der Web-Container beim Start)
    with app.app_context():
        db.create_all()

    # 5. Server Starten
    # debug=True ist okay lokal, aber use_reloader=False hilft gegen doppelte Logs
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
