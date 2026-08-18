"""Chargement des dépenses normalisées depuis PostgreSQL.

Ce module constitue la source de données commune du dashboard et de la page
d'analyse. Il ne lit ni la zone de staging, ni les exports locaux.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from database.connection import create_db_engine


EXPENSES_ANALYTICS_SQL = text(
    """
    SELECT
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
    """Retourne les données du dashboard issues des tables normalisées."""
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


def load_analysis_data() -> pd.DataFrame:
    """Retourne un périmètre analytique sans identifiant ni code projet réel."""
    dataframe = load_expenses()
    dataframe["project_status"] = dataframe["project_code"].map(
        lambda value: "Sans projet" if value == "SANS_PROJET" else "Avec projet"
    )
    project_values = dataframe["project_code"].where(
        dataframe["project_code"].ne("SANS_PROJET")
    )
    dataframe["_project_key"] = pd.factorize(project_values, sort=True)[0]
    return dataframe[
        [
            "expense_date",
            "expense_type",
            "amount_ttc",
            "billable",
            "project_status",
            "_project_key",
            "target",
        ]
    ].copy()
