"""Connexion PostgreSQL centralisée avec SQLAlchemy."""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


logger = logging.getLogger(__name__)


class DatabaseConfigurationError(RuntimeError):
    """Signale une configuration PostgreSQL absente ou invalide."""


def build_database_url() -> URL:
    """Construit l'URL SQLAlchemy depuis .env sans exposer le mot de passe."""
    load_dotenv()

    config = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "database": os.getenv("DB_NAME", "expenseai"),
        "username": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
    missing = [key for key in ("host", "username", "password") if not config[key]]
    if missing:
        names = ", ".join(missing)
        raise DatabaseConfigurationError(
            f"Variables PostgreSQL manquantes dans .env : {names}."
        )

    try:
        port = int(config["port"])
    except (TypeError, ValueError) as exc:
        raise DatabaseConfigurationError("DB_PORT doit être un entier.") from exc

    return URL.create(
        drivername="postgresql+psycopg2",
        username=config["username"],
        password=config["password"],
        host=config["host"],
        port=port,
        database=config["database"],
    )


def create_db_engine() -> Engine:
    """Crée un moteur SQLAlchemy ; la connexion reste ouverte à la demande."""
    return create_engine(
        build_database_url(),
        pool_pre_ping=True,
        pool_recycle=1_800,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000",
        },
    )


def check_database_connection(engine: Engine | None = None) -> tuple[bool, str]:
    """Teste PostgreSQL et retourne un résultat exploitable par une interface."""
    owns_engine = engine is None
    active_engine = engine
    try:
        active_engine = active_engine or create_db_engine()
        with active_engine.connect() as connection:
            database_name = connection.execute(text("SELECT current_database()"))
            database_name = database_name.scalar_one()
        return True, f"Connexion PostgreSQL établie avec la base {database_name}."
    except (DatabaseConfigurationError, SQLAlchemyError) as exc:
        logger.warning(
            "Connexion PostgreSQL impossible (%s).", type(exc).__name__
        )
        return False, "Connexion PostgreSQL indisponible. Vérifiez .env et le serveur."
    finally:
        if owns_engine and active_engine is not None:
            active_engine.dispose()


def test_connection(engine: Engine | None = None) -> bool:
    """Teste la connexion, affiche un message lisible et retourne un booléen."""
    success, message = check_database_connection(engine)
    print(message)
    return success


@contextmanager
def get_db_session(engine: Engine | None = None) -> Iterator[Session]:
    """Fournit une session avec rollback automatique en cas d'exception."""
    active_engine = engine or create_db_engine()
    session_factory = sessionmaker(bind=active_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if engine is None:
            active_engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(0 if test_connection() else 1)
