"""Persistance des simulations de prédiction ExpenseAI dans PostgreSQL."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any

from sqlalchemy import Engine, text

from database.connection import create_db_engine


INSERT_PREDICTION_SQL = text(
    """
    INSERT INTO predictions (
        expense_id,
        predicted_target,
        probability,
        model_version
    )
    VALUES (
        :expense_id,
        :predicted_target,
        :probability,
        :model_version
    )
    RETURNING id
    """
)

PREDICTION_HISTORY_SQL = text(
    """
    SELECT
        created_at,
        predicted_target,
        probability,
        model_version
    FROM predictions
    ORDER BY created_at DESC, id DESC
    LIMIT :limit
    """
)

EXPENSE_TYPES_SQL = text(
    "SELECT name FROM expense_types ORDER BY name"
)
PROJECTS_SQL = text(
    "SELECT code FROM projects ORDER BY code"
)
TAX_RATES_SQL = text(
    """
    SELECT DISTINCT tax_rate
    FROM expenses
    WHERE tax_rate IS NOT NULL
    ORDER BY tax_rate
    """
)


def _dispose_owned_engine(engine: Engine, owns_engine: bool) -> None:
    """Libère uniquement les moteurs créés par le repository."""
    if owns_engine:
        engine.dispose()


def load_prediction_options(engine: Engine | None = None) -> dict[str, list[Any]]:
    """Charge les référentiels utiles au formulaire, sans donnée individuelle."""
    owns_engine = engine is None
    active_engine = engine or create_db_engine()
    try:
        with active_engine.connect() as connection:
            expense_types = list(
                connection.execute(EXPENSE_TYPES_SQL).scalars().all()
            )
            projects = list(connection.execute(PROJECTS_SQL).scalars().all())
            tax_rates = [
                float(value)
                for value in connection.execute(TAX_RATES_SQL).scalars().all()
            ]
    finally:
        _dispose_owned_engine(active_engine, owns_engine)

    return {
        "expense_types": expense_types,
        "projects": projects,
        "tax_rates": tax_rates,
    }


def save_prediction(
    predicted_target: int,
    probability: float,
    model_version: str,
    expense_id: int | None = None,
    engine: Engine | None = None,
) -> int:
    """Enregistre exactement une prédiction et retourne son identifiant."""
    if predicted_target not in (0, 1):
        raise ValueError("predicted_target doit valoir 0 ou 1.")
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability doit être comprise entre 0 et 1.")
    if not model_version or len(model_version) > 50:
        raise ValueError("model_version doit contenir entre 1 et 50 caractères.")
    if expense_id is not None and (not isinstance(expense_id, int) or expense_id <= 0):
        raise ValueError("expense_id doit être un entier positif ou None.")

    stored_probability = Decimal(str(probability)).quantize(
        Decimal("0.00001"),
        rounding=ROUND_HALF_UP,
    )
    owns_engine = engine is None
    active_engine = engine or create_db_engine()
    try:
        with active_engine.begin() as connection:
            prediction_id = connection.execute(
                INSERT_PREDICTION_SQL,
                {
                    "expense_id": expense_id,
                    "predicted_target": predicted_target,
                    "probability": stored_probability,
                    "model_version": model_version,
                },
            ).scalar_one()
    finally:
        _dispose_owned_engine(active_engine, owns_engine)
    return int(prediction_id)


def load_recent_predictions(
    limit: int = 10,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    """Retourne un historique récent sans identifiant de dépense ni donnée métier."""
    if not 1 <= limit <= 100:
        raise ValueError("limit doit être compris entre 1 et 100.")

    return load_prediction_history(limit=limit, engine=engine)


def load_prediction_history(
    limit: int = 5_000,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    """Retourne l'historique utilisateur, limité et sans identifiant technique."""
    if not 1 <= limit <= 5_000:
        raise ValueError("limit doit être compris entre 1 et 5 000.")

    owns_engine = engine is None
    active_engine = engine or create_db_engine()
    try:
        with active_engine.connect() as connection:
            rows = connection.execute(
                PREDICTION_HISTORY_SQL,
                {"limit": limit},
            ).mappings().all()
    finally:
        _dispose_owned_engine(active_engine, owns_engine)
    return [dict(row) for row in rows]
