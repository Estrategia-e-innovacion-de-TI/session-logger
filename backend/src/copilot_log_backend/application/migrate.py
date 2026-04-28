from __future__ import annotations

from copilot_log_backend.driven_adapters.postgres.database import create_postgres_engine, run_migrations

from .config import load_config


def main() -> None:
    config = load_config()
    if config.storage != "postgres":
        print("No migration required for storage:", config.storage)
        return
    engine = create_postgres_engine(config.database_url)
    run_migrations(engine)
    print("PostgreSQL migrations applied")


if __name__ == "__main__":
    main()
