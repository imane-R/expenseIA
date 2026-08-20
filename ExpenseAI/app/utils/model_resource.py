"""Chargement paresseux et mutualisé de l'artefact ExpenseAI."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "models" / "expenseai_model.joblib"


def _load_artifact_uncached(path: str) -> dict[str, Any]:
    """Délègue le chargement à la source de vérité ML, seulement à la demande."""
    from ml.predict import load_model_artifact

    return load_model_artifact(path)


@st.cache_resource(show_spinner="Chargement du modèle ExpenseAI…")
def _load_cached_artifact(path: str, modified_at_ns: int) -> dict[str, Any]:
    """Charge une version de fichier donnée ; le mtime invalide le cache."""
    del modified_at_ns
    return _load_artifact_uncached(path)


def predict_expense_cached(
    expense_data: Mapping[str, Any],
    artifact_path: str | Path = DEFAULT_ARTIFACT_PATH,
) -> dict[str, Any]:
    """Utilise le même artefact en mémoire pour toutes les prédictions suivantes."""
    resolved_path = Path(artifact_path).expanduser().resolve()
    modified_at_ns = resolved_path.stat().st_mtime_ns
    artifact = _load_cached_artifact(str(resolved_path), modified_at_ns)
    from ml.predict import predict_expense_with_artifact

    return predict_expense_with_artifact(expense_data, artifact)
