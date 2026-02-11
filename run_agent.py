import time

from dotenv import load_dotenv

from app.agent.worker import run_agent_cycle
from app.core.config import get_env_settings
from app.core.extensions import db
from app.core.localdb.models import AgentSettings
from app.core.utils import log_and_validate_env, setup_logging
from app.web import create_app

load_dotenv()

if __name__ == "__main__":
    # 1. Logging Setup
    logger = setup_logging()
    logger.info("Starting Agent ...")

    # 2. Env Validierung
    encryption_key = log_and_validate_env(logger, get_env_settings())

    # 3. App Context erstellen (Nötig für DB Zugriff)
    # Wir starten KEINEN Server, wir nutzen app nur als Hülle für die DB
    app = create_app(encryption_key)

    with app.app_context():
        db.create_all()

    # 4. Der Infinite Loop (Ersatz für Scheduler)
    while True:
        with app.app_context():
            try:
                # Polling Interval dynamisch aus DB lesen
                settings = AgentSettings.query.first()
                polling_interval = settings.polling_interval_seconds if settings else 60

                # Den eigentlichen Job ausführen
                # Hinweis: run_agent_cycle muss so angepasst sein,
                # dass es nicht erwartet, vom Scheduler aufgerufen zu werden.
                run_agent_cycle(app)

            except Exception as e:
                logger.error(f"❌ Error in worker cycle: {e}", exc_info=True)
                # Fallback Interval bei Fehler, damit wir nicht spammen
                polling_interval = 60

        # Schlafen bis zum nächsten Zyklus
        # logger.debug(f"Sleeping for {interval} seconds...")
        time.sleep(polling_interval)
