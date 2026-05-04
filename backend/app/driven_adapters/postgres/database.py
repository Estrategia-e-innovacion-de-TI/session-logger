from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def create_postgres_engine(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def run_migrations(engine: Engine) -> None:
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    for migration in sorted(migrations_dir.glob("*.sql")):
        sql = migration.read_text(encoding="utf-8")
        with engine.begin() as connection:
            connection.execute(text(sql))

