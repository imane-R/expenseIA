"""Chargement des dépenses normalisées depuis PostgreSQL.

Ce module constitue l'unique source de données du dashboard. Il ne lit ni le
fichier Excel brut, ni les exports présents dans ``data/processed``.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from database.connection import create_db_engine


EXPENSES_ANALYTICS_SQL = text(
    """
    SELECT
        e.expense_group,
        e.expense_date,
        et.name AS expense_type,
        e.amount_ttc,
        e.billable,
        COALESCE(p.code, 'SANS_PROJET') AS project_code,
        e.tax_rate,
        e.target
    FROM expenses AS e
    INNER JOIN expense_types AS et
        ON et.id = e.expense_type_id
    LEFT JOIN projects AS p
        ON p.id = e.project_id
    ORDER BY e.expense_date, e.id
    """
)


def load_expenses() -> pd.DataFrame:
    """Retourne les données analytiques issues des tables normalisées."""
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            dataframe = pd.read_sql(EXPENSES_ANALYTICS_SQL, connection)
    finally:
        engine.dispose()

    dataframe["expense_date"] = pd.to_datetime(
        dataframe["expense_date"], errors="coerce"
    )
    dataframe["amount_ttc"] = pd.to_numeric(
        dataframe["amount_ttc"], errors="coerce"
    )
    dataframe["tax_rate"] = pd.to_numeric(
        dataframe["tax_rate"], errors="coerce"
    )
    dataframe["target"] = pd.to_numeric(
        dataframe["target"], errors="coerce"
    ).astype("Int64")
    dataframe["billable"] = dataframe["billable"].astype("boolean")
    return dataframe
