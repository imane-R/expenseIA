"""Transformations métier et orchestration d'une soumission ExpenseAI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

from database.prediction_repository import save_prediction
from ml.predict import predict_expense


WITHOUT_PROJECT_LABEL = "Sans projet"
WITHOUT_PROJECT_CODE = "SANS_PROJET"


@dataclass(frozen=True)
class PredictionSubmission:
    """Résultat d'une soumission et état facultatif de sa persistance."""

    prediction: dict[str, Any]
    history_id: int | None
    history_error: Exception | None


def derive_date_features(expense_date: date | datetime) -> dict[str, int]:
    """Reproduit strictement les variables temporelles du preprocessing."""
    if isinstance(expense_date, datetime):
        expense_date = expense_date.date()
    if not isinstance(expense_date, date):
        raise TypeError("expense_date doit être une date Python.")

    weekday = expense_date.weekday()
    return {
        "annee": expense_date.year,
        "mois": expense_date.month,
        "jour": expense_date.day,
        "jour_semaine": weekday,
        "trimestre": (expense_date.month - 1) // 3 + 1,
        "est_weekend": int(weekday >= 5),
    }


def normalize_project_code(project_selection: str | None) -> str:
    """Convertit l'option visuelle Sans projet en modalité attendue par le modèle."""
    if project_selection is None or project_selection.strip() in {
        "",
        WITHOUT_PROJECT_LABEL,
        WITHOUT_PROJECT_CODE,
    }:
        return WITHOUT_PROJECT_CODE
    return project_selection.strip()


def percentage_to_tax_rate(percentage: float) -> float:
    """Convertit un pourcentage affiché, par exemple 20, en fraction 0,20."""
    if not math.isfinite(percentage) or not 0 <= percentage <= 100:
        raise ValueError("Le taux affiché doit être compris entre 0 et 100 %.")
    return float(percentage) / 100.0


def build_expense_data(
    *,
    expense_date: date | datetime,
    expense_type: str,
    amount_ttc: float,
    billable: bool,
    project_selection: str | None,
    tax_rate: float,
) -> dict[str, Any]:
    """Construit exactement les onze features enregistrées avec le modèle."""
    if not expense_type or not expense_type.strip():
        raise ValueError("Le type de dépense est obligatoire.")
    if not math.isfinite(amount_ttc) or amount_ttc < 0:
        raise ValueError("Le montant TTC doit être positif ou nul.")
    if not math.isfinite(tax_rate) or not 0 <= tax_rate <= 1:
        raise ValueError("Le taux de taxe transmis au modèle doit être entre 0 et 1.")

    expense_data: dict[str, Any] = {
        "type": expense_type.strip(),
        "amount_ttc": float(amount_ttc),
        "billable": bool(billable),
        "project_code": normalize_project_code(project_selection),
        "tax_rate": float(tax_rate),
    }
    expense_data.update(derive_date_features(expense_date))
    return expense_data


def submit_prediction(
    expense_data: Mapping[str, Any],
    predictor: Callable[[Mapping[str, Any]], dict[str, Any]] = predict_expense,
    saver: Callable[..., int] = save_prediction,
) -> PredictionSubmission:
    """Prédit une fois et tente un seul INSERT pour une soumission réelle."""
    prediction = predictor(expense_data)
    score_key = "probability" if "probability" in prediction else "risk_score"
    try:
        history_id = saver(
            predicted_target=int(prediction["predicted_target"]),
            probability=float(prediction[score_key]),
            model_version=str(prediction["model_version"]),
            expense_id=None,
        )
    except Exception as exc:  # La prédiction reste affichable si l'historique échoue.
        return PredictionSubmission(prediction, None, exc)
    return PredictionSubmission(prediction, history_id, None)
