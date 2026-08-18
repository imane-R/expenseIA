"""Tests unitaires de l'intégration Streamlit, sans PostgreSQL réel."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, Mock

from app.utils.prediction_service import (
    build_expense_data,
    derive_date_features,
    normalize_project_code,
    percentage_to_tax_rate,
    submit_prediction,
)
from database.prediction_repository import load_prediction_history, save_prediction


class TestPredictionFeatures(TestCase):
    def test_date_features_match_training_preprocessing(self) -> None:
        # Le 15 août 2026 est un samedi du troisième trimestre.
        features = derive_date_features(date(2026, 8, 15))
        self.assertEqual(
            features,
            {
                "annee": 2026,
                "mois": 8,
                "jour": 15,
                "jour_semaine": 5,
                "trimestre": 3,
                "est_weekend": 1,
            },
        )

    def test_without_project_is_converted_to_model_modality(self) -> None:
        self.assertEqual(normalize_project_code("Sans projet"), "SANS_PROJET")
        self.assertEqual(normalize_project_code(None), "SANS_PROJET")

    def test_displayed_tax_percentage_is_converted_to_fraction(self) -> None:
        self.assertAlmostEqual(percentage_to_tax_rate(20.0), 0.20)
        self.assertAlmostEqual(percentage_to_tax_rate(5.5), 0.055)

    def test_model_input_contains_only_expected_features(self) -> None:
        expense_data = build_expense_data(
            expense_date=date(2026, 8, 15),
            expense_type="TYPE_SYNTHETIQUE",
            amount_ttc=125.50,
            billable=True,
            project_selection="Sans projet",
            tax_rate=0.20,
        )
        self.assertEqual(
            list(expense_data),
            [
                "type",
                "amount_ttc",
                "billable",
                "project_code",
                "tax_rate",
                "annee",
                "mois",
                "jour",
                "jour_semaine",
                "trimestre",
                "est_weekend",
            ],
        )
        self.assertNotIn("expense_group", expense_data)
        self.assertNotIn("target", expense_data)
        self.assertNotIn("status", expense_data)


class TestPredictionSubmission(TestCase):
    def test_one_submission_calls_prediction_and_insert_once(self) -> None:
        predictor = Mock(
            return_value={
                "predicted_target": 1,
                "predicted_label": "Refusée",
                "probability": 0.068,
                "threshold": 0.04,
                "model_version": "synthetic-test",
                "calibration": "sigmoid",
            }
        )
        saver = Mock(return_value=123)
        expense_data = {"type": "TYPE_SYNTHETIQUE"}

        submission = submit_prediction(
            expense_data,
            predictor=predictor,
            saver=saver,
        )

        predictor.assert_called_once_with(expense_data)
        saver.assert_called_once_with(
            predicted_target=1,
            probability=0.068,
            model_version="synthetic-test",
            expense_id=None,
        )
        self.assertEqual(submission.history_id, 123)
        self.assertIsNone(submission.history_error)

    def test_persistence_error_does_not_hide_prediction(self) -> None:
        predictor = Mock(
            return_value={
                "predicted_target": 0,
                "risk_score": 0.01,
                "threshold": 0.04,
                "model_version": "synthetic-test",
                "calibration": "none",
            }
        )
        saver = Mock(side_effect=RuntimeError("base indisponible"))

        submission = submit_prediction(
            {"type": "TYPE_SYNTHETIQUE"},
            predictor=predictor,
            saver=saver,
        )

        self.assertEqual(submission.prediction["predicted_target"], 0)
        self.assertIsNone(submission.history_id)
        self.assertIsInstance(submission.history_error, RuntimeError)

    def test_repository_executes_one_mocked_insert(self) -> None:
        engine = MagicMock()
        connection = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        connection.execute.return_value.scalar_one.return_value = 77

        prediction_id = save_prediction(
            predicted_target=1,
            probability=0.068123,
            model_version="synthetic-test",
            expense_id=None,
            engine=engine,
        )

        self.assertEqual(prediction_id, 77)
        connection.execute.assert_called_once()
        parameters = connection.execute.call_args.args[1]
        self.assertEqual(parameters["predicted_target"], 1)
        self.assertEqual(parameters["probability"], Decimal("0.06812"))
        self.assertIsNone(parameters["expense_id"])
        engine.dispose.assert_not_called()

    def test_history_repository_returns_only_user_columns(self) -> None:
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.mappings.return_value.all.return_value = [
            {
                "created_at": "2026-08-18 12:00:00",
                "predicted_target": 1,
                "probability": Decimal("0.06812"),
                "model_version": "synthetic-test",
            }
        ]

        rows = load_prediction_history(limit=50, engine=engine)

        self.assertEqual(
            set(rows[0]),
            {"created_at", "predicted_target", "probability", "model_version"},
        )
        parameters = connection.execute.call_args.args[1]
        self.assertEqual(parameters, {"limit": 50})
        engine.dispose.assert_not_called()
