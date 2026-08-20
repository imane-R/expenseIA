"""Couche PostgreSQL du projet ExpenseAI.

Les modèles ORM sont résolus à la demande : importer ``database.connection``
ne doit pas initialiser tout le schéma SQLAlchemy.
"""

from __future__ import annotations

from typing import Any


__all__ = ["Base", "ExpenseType", "Project", "Expense", "Prediction"]


def __getattr__(name: str) -> Any:
    """Charge les modèles uniquement lorsqu'ils sont explicitement demandés."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from database import models

    return getattr(models, name)
