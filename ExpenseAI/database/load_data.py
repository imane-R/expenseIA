"""Import transactionnel du CSV préparé vers PostgreSQL."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import create_db_engine
from database.models import Expense, ExpenseType, Project


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "expenses_clean.csv"
EXPECTED_EXPENSE_COUNT = 7_070

REQUIRED_COLUMNS = {
    "expense_group",
    "Type",
    "Montant TTC devise système",
    "Facturable",
    "Code projet",
    "Taux de taxe",
    "annee",
    "mois",
    "jour",
    "jour_semaine",
    "trimestre",
    "est_weekend",
    "target",
}

ExpenseSignature = tuple[
    str, date, int, Decimal, bool, int | None, Decimal, int
]


@dataclass(frozen=True)
class ImportSummary:
    """Résultats utiles pour contrôler un import."""

    expense_types: int
    projects: int
    source_expenses: int
    inserted_expenses: int
    existing_expenses: int
    approved_expenses: int
    refused_expenses: int
    total_expenses_in_database: int


def _clean_required_text(series: pd.Series, column: str) -> pd.Series:
    """Nettoie une chaîne obligatoire et refuse les valeurs vides."""
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.mask(cleaned.eq(""))
    if cleaned.isna().any():
        raise ValueError(f"La colonne {column} contient une valeur vide.")
    return cleaned


def _to_decimal(value: object, quantum: str, column: str) -> Decimal:
    """Convertit une valeur en Decimal avec la précision PostgreSQL attendue."""
    try:
        return Decimal(str(value)).quantize(Decimal(quantum))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Valeur numérique invalide dans {column}: {value!r}") from exc


def _prepare_dataframe(csv_path: Path) -> pd.DataFrame:
    """Valide le CSV et reconstruit les valeurs nécessaires à l'import."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Fichier préparé introuvable : {csv_path}")

    dataframe = pd.read_csv(
        csv_path,
        dtype={
            "expense_group": "string",
            "Type": "string",
            "Code projet": "string",
        },
    )
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "Colonnes obligatoires absentes du CSV : "
            + ", ".join(sorted(missing_columns))
        )
    if len(dataframe) != EXPECTED_EXPENSE_COUNT:
        raise ValueError(
            f"Le CSV contient {len(dataframe)} lignes au lieu de "
            f"{EXPECTED_EXPENSE_COUNT}."
        )

    prepared = pd.DataFrame(index=dataframe.index)
    prepared["expense_group"] = _clean_required_text(
        dataframe["expense_group"], "expense_group"
    )
    prepared["expense_type"] = _clean_required_text(dataframe["Type"], "Type")

    project_code = dataframe["Code projet"].astype("string").str.strip()
    project_code = project_code.mask(project_code.eq(""))
    prepared["project_code"] = project_code.mask(project_code.eq("SANS_PROJET"))

    date_parts = dataframe[["annee", "mois", "jour"]].apply(
        pd.to_numeric, errors="coerce"
    )
    expense_dates = pd.to_datetime(
        {
            "year": date_parts["annee"],
            "month": date_parts["mois"],
            "day": date_parts["jour"],
        },
        errors="coerce",
    )
    if expense_dates.isna().any():
        raise ValueError("Une date ne peut pas être reconstruite depuis année/mois/jour.")
    prepared["expense_date"] = expense_dates.dt.date

    prepared["amount_ttc"] = pd.to_numeric(
        dataframe["Montant TTC devise système"], errors="coerce"
    )
    prepared["tax_rate"] = pd.to_numeric(
        dataframe["Taux de taxe"], errors="coerce"
    )
    if prepared[["amount_ttc", "tax_rate"]].isna().any().any():
        raise ValueError("Un montant ou un taux de taxe est invalide.")

    billable = pd.to_numeric(dataframe["Facturable"], errors="coerce")
    if billable.isna().any() or not set(billable.unique()).issubset({0, 1}):
        raise ValueError("Facturable doit contenir uniquement 0 ou 1.")
    prepared["billable"] = billable.astype(bool)

    target = pd.to_numeric(dataframe["target"], errors="coerce")
    if target.isna().any() or not set(target.unique()).issubset({0, 1}):
        raise ValueError("target doit contenir uniquement 0 ou 1.")
    prepared["target"] = target.astype("int8")

    return prepared


def _signature(
    expense_group: str,
    expense_date: date,
    expense_type_id: int,
    amount_ttc: Decimal,
    billable: bool,
    project_id: int | None,
    tax_rate: Decimal,
    target: int,
) -> ExpenseSignature:
    """Construit la signature stable utilisée pour rendre l'import idempotent."""
    return (
        expense_group,
        expense_date,
        expense_type_id,
        amount_ttc,
        billable,
        project_id,
        tax_rate,
        target,
    )


def load_expenses(csv_path: Path = DEFAULT_CSV_PATH) -> ImportSummary:
    """Importe le CSV dans une transaction et ignore les lignes déjà présentes."""
    dataframe = _prepare_dataframe(csv_path)
    engine = create_db_engine()

    try:
        with Session(engine) as session:
            with session.begin():
                # Empêche deux imports ExpenseAI de s'exécuter en même temps.
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "CAST(hashtext(:lock_name) AS BIGINT))"
                    ),
                    {"lock_name": "expenseai_load_expenses"},
                )

                type_names = sorted(dataframe["expense_type"].unique().tolist())
                session.execute(
                    postgresql_insert(ExpenseType)
                    .values([{"name": name} for name in type_names])
                    .on_conflict_do_nothing(index_elements=[ExpenseType.name])
                )
                type_ids = dict(
                    session.execute(
                        select(ExpenseType.name, ExpenseType.id).where(
                            ExpenseType.name.in_(type_names)
                        )
                    ).all()
                )

                project_codes = sorted(
                    dataframe["project_code"].dropna().unique().tolist()
                )
                if "SANS_PROJET" in project_codes:
                    raise ValueError("SANS_PROJET ne doit jamais devenir un projet réel.")
                if project_codes:
                    session.execute(
                        postgresql_insert(Project)
                        .values([{"code": code} for code in project_codes])
                        .on_conflict_do_nothing(index_elements=[Project.code])
                    )
                    project_ids = dict(
                        session.execute(
                            select(Project.code, Project.id).where(
                                Project.code.in_(project_codes)
                            )
                        ).all()
                    )
                else:
                    project_ids = {}

                mappings: list[dict[str, object]] = []
                input_signatures: set[ExpenseSignature] = set()
                for row in dataframe.itertuples(index=False):
                    expense_type_id = type_ids[row.expense_type]
                    project_id = (
                        project_ids[row.project_code]
                        if pd.notna(row.project_code)
                        else None
                    )
                    amount_ttc = _to_decimal(row.amount_ttc, "0.01", "amount_ttc")
                    tax_rate = _to_decimal(row.tax_rate, "0.0001", "tax_rate")
                    row_signature = _signature(
                        row.expense_group,
                        row.expense_date,
                        expense_type_id,
                        amount_ttc,
                        bool(row.billable),
                        project_id,
                        tax_rate,
                        int(row.target),
                    )
                    if row_signature in input_signatures:
                        raise ValueError(
                            "Le CSV contient deux dépenses identiques après normalisation."
                        )
                    input_signatures.add(row_signature)
                    mappings.append(
                        {
                            "expense_group": row.expense_group,
                            "expense_date": row.expense_date,
                            "expense_type_id": expense_type_id,
                            "amount_ttc": amount_ttc,
                            "billable": bool(row.billable),
                            "project_id": project_id,
                            "tax_rate": tax_rate,
                            "target": int(row.target),
                            "_signature": row_signature,
                        }
                    )

                groups = dataframe["expense_group"].unique().tolist()
                existing_rows = session.execute(
                    select(
                        Expense.expense_group,
                        Expense.expense_date,
                        Expense.expense_type_id,
                        Expense.amount_ttc,
                        Expense.billable,
                        Expense.project_id,
                        Expense.tax_rate,
                        Expense.target,
                    ).where(Expense.expense_group.in_(groups))
                ).all()
                existing_signatures = {
                    _signature(
                        row.expense_group,
                        row.expense_date,
                        row.expense_type_id,
                        row.amount_ttc,
                        row.billable,
                        row.project_id,
                        row.tax_rate,
                        row.target,
                    )
                    for row in existing_rows
                }

                new_mappings = [
                    {key: value for key, value in mapping.items() if key != "_signature"}
                    for mapping in mappings
                    if mapping["_signature"] not in existing_signatures
                ]
                if new_mappings:
                    session.execute(insert(Expense), new_mappings)

                existing_from_source = len(input_signatures & existing_signatures)
                if existing_from_source + len(new_mappings) != EXPECTED_EXPENSE_COUNT:
                    raise RuntimeError(
                        "Le contrôle d'idempotence ne couvre pas les 7 070 dépenses."
                    )

                total_expenses = session.scalar(
                    select(text("COUNT(*)")).select_from(Expense)
                )

                summary = ImportSummary(
                    expense_types=len(type_names),
                    projects=len(project_codes),
                    source_expenses=len(dataframe),
                    inserted_expenses=len(new_mappings),
                    existing_expenses=existing_from_source,
                    approved_expenses=int((dataframe["target"] == 0).sum()),
                    refused_expenses=int((dataframe["target"] == 1).sum()),
                    total_expenses_in_database=int(total_expenses or 0),
                )
    except (SQLAlchemyError, ValueError, RuntimeError):
        logger.exception("Import annulé : la transaction PostgreSQL a été rollbackée.")
        raise

    return summary


def print_summary(summary: ImportSummary) -> None:
    """Affiche les contrôles demandés après validation de la transaction."""
    print(f"Types de dépenses référencés : {summary.expense_types}")
    print(f"Projets réels référencés : {summary.projects}")
    print(f"Dépenses vérifiées depuis le CSV : {summary.source_expenses}")
    print(f"Dépenses nouvellement insérées : {summary.inserted_expenses}")
    print(f"Dépenses déjà présentes : {summary.existing_expenses}")
    print(f"Dépenses approuvées : {summary.approved_expenses}")
    print(f"Dépenses refusées : {summary.refused_expenses}")
    print(f"Total actuel dans expenses : {summary.total_expenses_in_database}")


def main() -> int:
    """Point d'entrée en ligne de commande."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        summary = load_expenses()
    except (FileNotFoundError, SQLAlchemyError, ValueError, RuntimeError) as exc:
        logger.error("Échec de l'import : %s", exc)
        return 1
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
