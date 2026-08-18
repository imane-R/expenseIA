"""Tests synthétiques de l'API de prédiction ExpenseAI."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import warnings

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.predict import load_model_artifact, predict_expense


warnings.filterwarnings(
    "ignore",
    message="Setting the shape on a NumPy array has been deprecated.*",
    category=DeprecationWarning,
)


def synthetic_expense(
    expense_type: str = "TYPE_SYNTHETIQUE_INCONNU",
    project_code: str = "PROJET_SYNTHETIQUE_INCONNU",
) -> dict[str, object]:
    """Retourne une ligne fictive sans donnée réelle ni identifiant métier."""
    return {
        "type": expense_type,
        "amount_ttc": 125.50,
        "billable": 0,
        "project_code": project_code,
        "tax_rate": 0.20,
        "annee": 2026,
        "mois": 6,
        "jour": 15,
        "jour_semaine": 0,
        "trimestre": 2,
        "est_weekend": 0,
    }


class TestExpensePrediction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # L'artefact de test est appris uniquement sur des lignes fictives afin
        # que les tests restent autonomes et ne contiennent aucune donnée réelle.
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.artifact_path = Path(cls.temporary_directory.name) / "synthetic.joblib"

        synthetic_rows = []
        for index in range(8):
            row = synthetic_expense(
                expense_type="TYPE_A" if index % 2 == 0 else "TYPE_B",
                project_code="PROJET_A" if index < 4 else "PROJET_B",
            )
            row["amount_ttc"] = 25.0 + index * 50.0
            row["billable"] = index % 2
            synthetic_rows.append(row)
        training_frame = pd.DataFrame(synthetic_rows)
        training_target = pd.Series([0, 1, 0, 1, 0, 1, 0, 1])
        features = list(synthetic_rows[0])

        preprocessing = ColumnTransformer(
            transformers=[
                (
                    "categories",
                    OneHotEncoder(handle_unknown="ignore"),
                    ["type", "project_code"],
                ),
                (
                    "numeriques",
                    StandardScaler(),
                    [feature for feature in features if feature not in {"type", "project_code"}],
                ),
            ]
        )
        model = Pipeline(
            [
                ("preprocessing", preprocessing),
                ("model", LogisticRegression(random_state=42, max_iter=1000)),
            ]
        )
        model.fit(training_frame, training_target)
        joblib.dump(
            {
                "model": model,
                "threshold": 0.5,
                "features": features,
                "model_version": "synthetic-test",
                "calibration": "none",
                "score_name": "risk_score",
            },
            cls.artifact_path,
        )

        cls.artifact = load_model_artifact(cls.artifact_path)
        cls.score_name = str(cls.artifact["score_name"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_artifact_loads_with_complete_structure(self) -> None:
        self.assertIn("model", self.artifact)
        self.assertEqual(len(self.artifact["features"]), 11)

    def test_prediction_structure_and_score_range(self) -> None:
        result = predict_expense(synthetic_expense(), self.artifact_path)
        self.assertIn(result["predicted_target"], (0, 1))
        self.assertIn(result["predicted_label"], ("Approuvée", "Refusée"))
        self.assertIn(self.score_name, result)
        self.assertGreaterEqual(result[self.score_name], 0.0)
        self.assertLessEqual(result[self.score_name], 1.0)

    def test_label_is_consistent_with_saved_threshold(self) -> None:
        result = predict_expense(synthetic_expense(), self.artifact_path)
        expected_target = int(result[self.score_name] >= result["threshold"])
        expected_label = "Refusée" if expected_target == 1 else "Approuvée"
        self.assertEqual(result["predicted_target"], expected_target)
        self.assertEqual(result["predicted_label"], expected_label)

    def test_unknown_categories_are_accepted(self) -> None:
        result = predict_expense(
            synthetic_expense(
                expense_type="NOUVEAU_TYPE_JAMAIS_VU",
                project_code="NOUVEAU_PROJET_JAMAIS_VU",
            ),
            self.artifact_path,
        )
        self.assertIn(self.score_name, result)

    def test_expense_group_is_not_required(self) -> None:
        row = synthetic_expense()
        self.assertNotIn("expense_group", row)
        result = predict_expense(row, self.artifact_path)
        self.assertIn("predicted_target", result)

    def test_missing_feature_is_rejected(self) -> None:
        row = synthetic_expense()
        row.pop("amount_ttc")
        with self.assertRaisesRegex(ValueError, "amount_ttc"):
            predict_expense(row, self.artifact_path)


if __name__ == "__main__":
    unittest.main()
