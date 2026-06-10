from __future__ import annotations

import logging
import os
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def run_incremental_ingest(app) -> None:
    """APScheduler job: pull new records from SODA and upsert them."""
    from crime_detector.ingestion.client import ArcGISClient
    from crime_detector.ingestion.normalizer import normalize
    from crime_detector.storage.repository import CrimeRepository
    from crime_detector.extensions import db

    with app.app_context():
        repo = CrimeRepository(db.session)
        since = repo.get_last_ingest_timestamp()
        logger.info("Starting incremental ingest since %s", since)

        client = ArcGISClient(
            endpoint=app.config["ARCGIS_ENDPOINT"],
            page_size=app.config["PAGE_SIZE"],
        )

        records = []
        skipped = 0
        for raw in client.fetch_all(since=since):
            rec = normalize(raw)
            if rec is None:
                skipped += 1
                continue
            records.append(rec)
            if len(records) >= 5000:
                repo.upsert_batch(records)
                logger.info("Upserted batch of %d records", len(records))
                records = []

        if records:
            repo.upsert_batch(records)

        logger.info("Ingest complete. Upserted %d, skipped %d", len(records), skipped)


def register_scheduler(app) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # Run every hour by default; override via INGEST_CRON_HOUR env var
    hour_interval = int(os.environ.get("INGEST_INTERVAL_HOURS", "1"))
    scheduler.add_job(
        run_incremental_ingest,
        "interval",
        hours=hour_interval,
        args=[app],
        id="incremental_ingest",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started; ingest every %d hour(s)", hour_interval)
    return scheduler


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")

    from crime_detector import create_app

    application = create_app(os.environ.get("FLASK_ENV", "production"))

    # Run one immediate ingest on startup, then schedule recurring ones
    run_incremental_ingest(application)
    scheduler = register_scheduler(application)

    try:
        Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
