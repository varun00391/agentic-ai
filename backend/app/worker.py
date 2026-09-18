import time

from app.config import get_settings
from app.db import bootstrap_if_needed, get_session_factory, init_engine
from app.jobs import process_available_jobs


def main() -> None:
    settings = get_settings()
    init_engine(settings)
    bootstrap_if_needed(settings)
    factory = get_session_factory()
    while True:
        session = factory()
        try:
            processed = process_available_jobs(session, settings)
        finally:
            session.close()
        if processed == 0:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
