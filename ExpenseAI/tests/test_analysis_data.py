"""Tests de la projection confidentielle utilisée par la page Analyse."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd
from sqlalchemy.exc import OperationalError

from app.utils.data_loader import load_analysis_data, load_expenses


class TestAnalysisData(TestCase):
    @patch("app.utils.data_loader._read_expenses")
    def test_stale_shared_pool_is_recreated_once(self, mocked_read) -> None:
        expected = pd.DataFrame(
            {
                "expense_date": [],
                "expense_type": [],
                "amount_ttc": [],
                "billable": [],
                "project_code": [],
                "tax_rate": [],
                "target": [],
            }
        )
        mocked_read.side_effect = [
            OperationalError("SELECT", {}, RuntimeError("connexion fermée")),
            expected,
        ]
        engine = MagicMock()

        result = load_expenses(engine=engine)

        self.assertEqual(list(result.columns), list(expected.columns))
        self.assertEqual(mocked_read.call_count, 2)
        engine.dispose.assert_called_once_with()

    @patch("app.utils.data_loader.load_expenses")
    def test_project_codes_are_replaced_with_anonymous_dimensions(
        self, mocked_load_expenses
    ) -> None:
        mocked_load_expenses.return_value = pd.DataFrame(
            {
                "expense_date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "expense_type": ["Repas", "Transport"],
                "amount_ttc": [20.0, 40.0],
                "billable": [True, False],
                "project_code": ["PROJET_CONFIDENTIEL", "SANS_PROJET"],
                "tax_rate": [0.2, 0.1],
                "target": pd.Series([0, 1], dtype="Int64"),
            }
        )

        analysis = load_analysis_data()

        self.assertNotIn("project_code", analysis.columns)
        self.assertNotIn("expense_group", analysis.columns)
        self.assertEqual(
            analysis["project_status"].tolist(), ["Avec projet", "Sans projet"]
        )
        self.assertGreaterEqual(int(analysis.loc[0, "_project_key"]), 0)
        self.assertEqual(int(analysis.loc[1, "_project_key"]), -1)


if __name__ == "__main__":
    import unittest

    unittest.main()
