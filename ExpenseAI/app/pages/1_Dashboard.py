"""Dashboard exploratoire des dépenses normalisées ExpenseAI."""

from __future__ import annotations

from time import perf_counter

PAGE_STARTED_AT = perf_counter()

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from app.utils.data_loader import load_expenses
from perf_diagnostics import log_duration


log_duration("Dashboard - imports", PAGE_STARTED_AT)


LOGGER = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 600
STATUS_LABELS = {0: "Approuvée", 1: "Refusée"}
STATUS_COLORS = {"Approuvée": "#2563EB", "Refusée": "#DC2626"}
FILTER_KEYS = (
    "dashboard_period",
    "dashboard_status",
    "dashboard_types",
    "dashboard_projects",
    "dashboard_billable",
)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Chargement depuis PostgreSQL…")
def load_dashboard_data() -> pd.DataFrame:
    """Charge une seule fois les colonnes utiles au dashboard."""
    from app.utils.db_resources import get_database_engine

    return load_expenses(engine=get_database_engine())


def reset_filters() -> None:
    """Rétablit les valeurs par défaut des filtres."""
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def format_euro(value: float) -> str:
    """Formate un montant en euros selon une présentation française."""
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def add_percentage_labels(frame: pd.DataFrame, count_column: str) -> pd.DataFrame:
    """Ajoute un libellé accessible combinant effectif et pourcentage."""
    result = frame.copy()
    total = result[count_column].sum()
    result["percentage"] = (
        result[count_column].div(total).mul(100) if total else 0.0
    )
    result["label"] = result.apply(
        lambda row: f"{int(row[count_column]):,} ({row['percentage']:.1f} %)".replace(
            ",", " "
        ),
        axis=1,
    )
    return result


st.title("Dashboard des dépenses")
st.caption(
    "Indicateurs calculés à partir des tables PostgreSQL normalisées. "
    "Aucune donnée brute de staging n’est utilisée."
)

data_started_at = perf_counter()
try:
    expenses = load_dashboard_data()
except Exception as exc:  # Le détail technique n'est jamais exposé dans l'interface.
    LOGGER.exception("Échec du chargement PostgreSQL", exc_info=exc)
    st.error(
        "Les données PostgreSQL sont momentanément indisponibles. "
        "Vérifiez la configuration de la base et réessayez."
    )
    st.stop()
log_duration("Dashboard - données PostgreSQL", data_started_at)

if expenses.empty:
    st.error("La requête PostgreSQL n’a retourné aucune dépense à analyser.")
    st.stop()

required_columns = {
    "expense_date",
    "expense_type",
    "amount_ttc",
    "billable",
    "project_code",
    "tax_rate",
    "target",
}
if not required_columns.issubset(expenses.columns):
    st.error("Les données chargées ne respectent pas le schéma analytique attendu.")
    st.stop()

if expenses["expense_date"].isna().any() or not set(
    expenses["target"].dropna().astype(int).unique()
).issubset(STATUS_LABELS):
    st.error("Des dates ou des valeurs de cible invalides empêchent l’analyse.")
    st.stop()

expenses = expenses.copy()
expenses["status"] = expenses["target"].astype(int).map(STATUS_LABELS)

min_date = expenses["expense_date"].min().date()
max_date = expenses["expense_date"].max().date()
all_statuses = list(STATUS_LABELS.values())
all_types = sorted(expenses["expense_type"].dropna().unique().tolist())
all_projects = sorted(expenses["project_code"].dropna().unique().tolist())

with st.sidebar:
    st.header("Filtres")
    st.button(
        "Réinitialiser les filtres",
        on_click=reset_filters,
        width="stretch",
    )
    selected_period = st.date_input(
        "Période",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="dashboard_period",
    )
    selected_statuses = st.multiselect(
        "Statut",
        options=all_statuses,
        default=all_statuses,
        key="dashboard_status",
    )
    selected_types = st.multiselect(
        "Type de dépense",
        options=all_types,
        default=[],
        help="Laisser vide pour inclure tous les types.",
        key="dashboard_types",
    )
    selected_projects = st.multiselect(
        "Projet",
        options=all_projects,
        default=[],
        help="Laisser vide pour inclure tous les projets.",
        key="dashboard_projects",
    )
    selected_billable = st.selectbox(
        "Facturable",
        options=("Tous", "Oui", "Non"),
        key="dashboard_billable",
    )

filtered = expenses.copy()
if isinstance(selected_period, (tuple, list)) and len(selected_period) == 2:
    start_date, end_date = selected_period
elif isinstance(selected_period, (tuple, list)) and len(selected_period) == 1:
    start_date = end_date = selected_period[0]
else:
    start_date = end_date = selected_period

filtered = filtered[
    filtered["expense_date"].dt.date.between(start_date, end_date)
]
filtered = filtered[filtered["status"].isin(selected_statuses)]
if selected_types:
    filtered = filtered[filtered["expense_type"].isin(selected_types)]
if selected_projects:
    filtered = filtered[filtered["project_code"].isin(selected_projects)]
if selected_billable != "Tous":
    filtered = filtered[filtered["billable"].eq(selected_billable == "Oui")]

if filtered.empty:
    st.warning("Aucune dépense ne correspond à la combinaison de filtres choisie.")
    st.stop()

row_count = len(filtered)
total_amount = filtered["amount_ttc"].sum()
mean_amount = filtered["amount_ttc"].mean()
approval_rate = filtered["target"].eq(0).mean() * 100
refusal_rate = filtered["target"].eq(1).mean() * 100

st.subheader("Indicateurs clés")
kpi_columns = st.columns(5)
kpi_columns[0].metric("Lignes de dépense", f"{row_count:,}".replace(",", " "))
kpi_columns[1].metric("Montant TTC total", format_euro(total_amount))
kpi_columns[2].metric("Montant TTC moyen", format_euro(mean_amount))
kpi_columns[3].metric("Taux d’approbation", f"{approval_rate:.1f} %")
kpi_columns[4].metric("Taux de refus", f"{refusal_rate:.1f} %")

monthly = (
    filtered.assign(month=filtered["expense_date"].dt.to_period("M").dt.to_timestamp())
    .groupby("month", as_index=False)
    .agg(expense_count=("target", "size"))
)
monthly_figure = px.line(
    monthly,
    x="month",
    y="expense_count",
    markers=True,
    labels={"month": "Mois", "expense_count": "Nombre de lignes"},
    title="Évolution mensuelle du volume de dépenses",
)
monthly_figure.update_traces(line_color="#2563EB")
monthly_figure.update_layout(hovermode="x unified")
st.plotly_chart(monthly_figure, width="stretch")

left_column, right_column = st.columns(2)

status_summary = (
    filtered.groupby("status", observed=True)
    .size()
    .rename("expense_count")
    .reset_index()
)
status_summary = add_percentage_labels(status_summary, "expense_count")
status_figure = px.bar(
    status_summary,
    x="status",
    y="expense_count",
    color="status",
    text="label",
    color_discrete_map=STATUS_COLORS,
    labels={"status": "Statut", "expense_count": "Nombre de lignes"},
    title="Répartition des statuts",
)
status_figure.update_layout(showlegend=False)
status_figure.update_traces(textposition="outside")
left_column.plotly_chart(status_figure, width="stretch")

billable_summary = (
    filtered.assign(
        facturable=filtered["billable"].map({True: "Oui", False: "Non"})
    )
    .groupby("facturable", observed=True)
    .agg(
        expense_count=("target", "size"),
        refusal_rate=("target", "mean"),
    )
    .reset_index()
)
billable_summary["refusal_rate"] *= 100
billable_summary["label"] = billable_summary.apply(
    lambda row: f"n = {int(row['expense_count']):,} · {row['refusal_rate']:.1f} % refus".replace(
        ",", " "
    ),
    axis=1,
)
billable_figure = px.bar(
    billable_summary,
    x="facturable",
    y="expense_count",
    color="facturable",
    text="label",
    color_discrete_map={"Oui": "#0F766E", "Non": "#64748B"},
    labels={"facturable": "Facturable", "expense_count": "Nombre de lignes"},
    title="Volume et taux de refus selon le caractère facturable",
)
billable_figure.update_layout(showlegend=False)
billable_figure.update_traces(textposition="outside")
right_column.plotly_chart(billable_figure, width="stretch")

type_summary = (
    filtered.groupby("expense_type", observed=True)
    .agg(
        expense_count=("target", "size"),
        total_amount=("amount_ttc", "sum"),
        mean_amount=("amount_ttc", "mean"),
        refusal_count=("target", "sum"),
        refusal_rate=("target", "mean"),
    )
    .reset_index()
)
type_summary["refusal_rate"] *= 100

st.subheader("Types de dépense")
volume_tab, amount_tab = st.tabs(("Volume", "Montant TTC"))
with volume_tab:
    type_volume = type_summary.nlargest(15, "expense_count").sort_values(
        "expense_count"
    )
    type_volume_figure = px.bar(
        type_volume,
        x="expense_count",
        y="expense_type",
        orientation="h",
        text="expense_count",
        labels={
            "expense_count": "Nombre de lignes",
            "expense_type": "Type de dépense",
        },
        title="15 types les plus fréquents",
    )
    type_volume_figure.update_traces(marker_color="#2563EB")
    st.plotly_chart(type_volume_figure, width="stretch")
with amount_tab:
    type_amount = type_summary.nlargest(15, "total_amount").sort_values(
        "total_amount"
    )
    type_amount_figure = px.bar(
        type_amount,
        x="total_amount",
        y="expense_type",
        orientation="h",
        text_auto=".3s",
        labels={
            "total_amount": "Montant TTC total (€)",
            "expense_type": "Type de dépense",
        },
        title="15 types représentant les montants TTC les plus élevés",
    )
    type_amount_figure.update_traces(marker_color="#0F766E")
    st.plotly_chart(type_amount_figure, width="stretch")

reliable_type_rates = type_summary[type_summary["expense_count"] >= 20].copy()
reliable_type_rates["label"] = reliable_type_rates.apply(
    lambda row: f"{row['refusal_rate']:.1f} % (n = {int(row['expense_count'])})",
    axis=1,
)
reliable_type_rates = reliable_type_rates.sort_values("refusal_rate").tail(15)
st.subheader("Taux de refus par type")
st.caption(
    "Seuls les types comptant au moins 20 lignes dans le périmètre filtré sont "
    "affichés ; l’effectif (n) accompagne chaque taux."
)
if reliable_type_rates.empty:
    st.info("Aucun type n’atteint le seuil minimal de 20 lignes.")
else:
    refusal_figure = px.bar(
        reliable_type_rates,
        x="refusal_rate",
        y="expense_type",
        orientation="h",
        text="label",
        labels={
            "refusal_rate": "Taux de refus (%)",
            "expense_type": "Type de dépense",
        },
        title="Types présentant les taux de refus les plus élevés",
    )
    refusal_figure.update_traces(marker_color="#DC2626", textposition="outside")
    st.plotly_chart(refusal_figure, width="stretch")

st.subheader("Distribution des montants TTC")
distribution_tab, comparison_tab = st.tabs(("Distribution", "Comparaison par statut"))
with distribution_tab:
    histogram_figure = px.histogram(
        filtered,
        x="amount_ttc",
        nbins=50,
        labels={"amount_ttc": "Montant TTC (€)"},
        title="Distribution des montants TTC (valeurs extrêmes conservées)",
    )
    histogram_figure.update_traces(marker_color="#2563EB")
    histogram_figure.update_yaxes(title="Nombre de lignes")
    st.plotly_chart(histogram_figure, width="stretch")
with comparison_tab:
    box_figure = px.box(
        filtered,
        x="status",
        y="amount_ttc",
        color="status",
        color_discrete_map=STATUS_COLORS,
        points="outliers",
        labels={"status": "Statut", "amount_ttc": "Montant TTC (€)"},
        title="Montants TTC selon le statut",
    )
    box_figure.update_layout(showlegend=False)
    st.plotly_chart(box_figure, width="stretch")

st.subheader("Détail agrégé par type")
display_summary = type_summary.rename(
    columns={
        "expense_type": "Type de dépense",
        "expense_count": "Nombre de lignes",
        "total_amount": "Montant TTC total (€)",
        "mean_amount": "Montant TTC moyen (€)",
        "refusal_count": "Nombre de refus",
        "refusal_rate": "Taux de refus (%)",
    }
).sort_values("Nombre de lignes", ascending=False)
display_summary["Montant TTC total (€)"] = display_summary[
    "Montant TTC total (€)"
].round(2)
display_summary["Montant TTC moyen (€)"] = display_summary[
    "Montant TTC moyen (€)"
].round(2)
display_summary["Taux de refus (%)"] = display_summary[
    "Taux de refus (%)"
].round(2)
st.dataframe(display_summary, hide_index=True, width="stretch")
st.download_button(
    "Télécharger ce tableau agrégé (CSV)",
    data=display_summary.to_csv(index=False).encode("utf-8-sig"),
    file_name="expenseai_dashboard_agrege.csv",
    mime="text/csv",
)

log_duration("Dashboard - total", PAGE_STARTED_AT)
