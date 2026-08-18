"""API de prédiction locale pour l'artefact final ExpenseAI.

Le module ne se connecte ni à PostgreSQL ni à Streamlit. Il charge l'artefact
complet sauvegardé par ``06_final_model.ipynb`` et applique le seuil verrouillé.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import warnings

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "models" / "expenseai_model.joblib"
REQUIRED_ARTIFACT_KEYS = {
    "model",
    "threshold",
    "features",
    "model_version",
    "calibration",
    "score_name",
}


def load_model_artifact(
    artifact_path: str | Path = DEFAULT_ARTIFACT_PATH,
) -> dict[str, Any]:
    """Charge et valide la structure minimale de l'artefact ExpenseAI."""
    resolved_path = Path(artifact_path).expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Artefact ExpenseAI introuvable : {resolved_path}")

    # joblib 1.5 émet avec NumPy 2.5 un avertissement de compatibilité connu
    # pendant le rechargement de certains tableaux scikit-learn. Il n'affecte
    # ni les valeurs restaurées ni la prédiction et reste limité à ce bloc.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Setting the shape on a NumPy array has been deprecated.*",
            category=DeprecationWarning,
        )
        artifact = joblib.load(resolved_path)
    if not isinstance(artifact, dict):
        raise TypeError("L'artefact ExpenseAI doit être un dictionnaire.")

    missing_keys = REQUIRED_ARTIFACT_KEYS.difference(artifact)
    if missing_keys:
        raise ValueError(
            "Artefact ExpenseAI incomplet. Clés absentes : "
            + ", ".join(sorted(missing_keys))
        )
    return artifact


def _prepare_input(
    expense_data: Mapping[str, Any] | pd.DataFrame,
    expected_features: list[str],
) -> pd.DataFrame:
    """Construit un DataFrame ordonné et refuse les features obligatoires absentes."""
    if isinstance(expense_data, pd.DataFrame):
        frame = expense_data.copy()
    elif isinstance(expense_data, Mapping):
        frame = pd.DataFrame([dict(expense_data)])
    else:
        raise TypeError("expense_data doit être un mapping ou un DataFrame pandas.")

    missing_features = [
        feature for feature in expected_features if feature not in frame.columns
    ]
    if missing_features:
        raise ValueError(
            "Variables requises absentes : " + ", ".join(missing_features)
        )
    return frame.loc[:, expected_features]


def predict_expense(
    expense_data: Mapping[str, Any] | pd.DataFrame,
    artifact_path: str | Path = DEFAULT_ARTIFACT_PATH,
) -> dict[str, Any]:
    """Estime le risque de refus d'une ligne de dépense.

    ``expense_group`` n'est pas nécessaire : cet identifiant sert uniquement à
    préserver les groupes pendant l'évaluation et n'est jamais une feature.
    """
    artifact = load_model_artifact(artifact_path)
    expected_features = list(artifact["features"])
    frame = _prepare_input(expense_data, expected_features)

    score = float(artifact["model"].predict_proba(frame)[:, 1][0])
    threshold = float(artifact["threshold"])
    predicted_target = int(score >= threshold)
    score_name = str(artifact["score_name"])

    result: dict[str, Any] = {
        "predicted_target": predicted_target,
        "predicted_label": "Refusée" if predicted_target == 1 else "Approuvée",
        score_name: score,
        "threshold": threshold,
        "model_version": str(artifact["model_version"]),
        "calibration": str(artifact["calibration"]),
    }
    return result
