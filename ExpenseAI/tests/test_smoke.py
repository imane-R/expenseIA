"""Tests légers ne nécessitant ni serveur Streamlit ni PostgreSQL."""

import unittest

from database.models import Base, Expense, ExpenseType, Prediction, Project


class TestProjectStructure(unittest.TestCase):
    def test_database_models_are_registered(self) -> None:
        expected_tables = {
            ExpenseType.__tablename__,
            Project.__tablename__,
            Expense.__tablename__,
            Prediction.__tablename__,
        }
        self.assertTrue(expected_tables.issubset(Base.metadata.tables))

    def test_expense_foreign_keys_match_schema(self) -> None:
        expense_table = Base.metadata.tables["expenses"]
        foreign_keys = {
            (foreign_key.parent.name, foreign_key.target_fullname)
            for foreign_key in expense_table.foreign_keys
        }
        self.assertEqual(
            foreign_keys,
            {
                ("expense_type_id", "expense_types.id"),
                ("project_id", "projects.id"),
            },
        )

    def test_expense_indexes_match_schema(self) -> None:
        index_names = {
            index.name for index in Base.metadata.tables["expenses"].indexes
        }
        self.assertEqual(
            index_names,
            {
                "ix_expenses_expense_group",
                "ix_expenses_expense_date",
                "ix_expenses_expense_type_id",
                "ix_expenses_project_id",
            },
        )

    def test_prediction_constraints_are_registered(self) -> None:
        constraint_names = {
            constraint.name
            for constraint in Base.metadata.tables["predictions"].constraints
            if constraint.name
        }
        self.assertIn("ck_predictions_target", constraint_names)
        self.assertIn("ck_predictions_probability", constraint_names)


if __name__ == "__main__":
    unittest.main()
