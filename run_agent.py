import asyncio

from dotenv import load_dotenv

from app.agent.worker import run_agent_cycle
from app.core.config import get_env_settings
from app.core.extensions import db
from app.core.utils import log_and_validate_env, setup_logging
from app.web import create_app
from app.agent.runtime import RuntimeSetting, prepare_runtime

load_dotenv()


async def main():
    # 1. Logging Setup
    logger = setup_logging()
    logger.info("Starting Agent (Async)...")

    # 2. Env Validierung
    encryption_key = log_and_validate_env(logger, get_env_settings())

    # 3. App Context erstellen (Nötig für DB Zugriff)
    # Wir starten KEINEN Server, wir nutzen app nur als Hülle für die DB
    app = create_app(encryption_key)

    with app.app_context():
        db.create_all()

    # 4. Der Infinite Loop
    while True:
        polling_interval = 60
        try:
            # Synchrone DB-Abfrage muss in einem Thread oder Sync-Kontext passieren.
            # Da SQLAlchemy lazy loading etc. macht, ist es am sichersten,
            # dies kurz synchron zu machen.
            with app.app_context():
                runtime: RuntimeSetting | None = prepare_runtime()
                if not runtime:
                    logger.error("No runtime found, skipping cycle")
                    return
                polling_interval = runtime.agent_settings.polling_interval_seconds
                # Den eigentlichen Job ausführen
                await run_agent_cycle(runtime)

        except Exception as e:
            logger.error("Error in main: %s", e, exc_info=True)
            # Fallback Interval bei Fehler
            polling_interval = 60

        # Schlafen bis zum nächsten Zyklus (non-blocking)
        await asyncio.sleep(polling_interval)


if __name__ == "__main__":
    asyncio.run(main())
