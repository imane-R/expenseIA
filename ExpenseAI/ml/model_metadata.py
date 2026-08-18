"""Lecture contrôlée des métadonnées du modèle ExpenseAI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_PATH = PROJECT_ROOT / "models" / "expenseai_model_metadata.json"
REQUIRED_METADATA_KEYS = {
    "model_name",
    "model_version",
    "threshold",
    "calibration",
    "features",
    "test_metrics",
    "confusion_matrix",
}


def load_model_metadata(
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
) -> dict[str, Any]:
    """Charge le JSON final et vérifie les champs utilisés par l'interface."""
    resolved_path = Path(metadata_path).expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Métadonnées ExpenseAI introuvables : {resolved_path}"
        )

    with resolved_path.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)
    if not isinstance(metadata, dict):
        raise TypeError("Les métadonnées ExpenseAI doivent former un objet JSON.")

    missing_keys = REQUIRED_METADATA_KEYS.difference(metadata)
    if missing_keys:
        raise ValueError(
            "Métadonnées ExpenseAI incomplètes. Clés absentes : "
            + ", ".join(sorted(missing_keys))
        )
    return metadata
