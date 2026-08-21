"""Exploration détaillée des dépenses normalisées ExpenseAI."""

from __future__ import annotations

from time import perf_counter

PAGE_STARTED_AT = perf_counter()

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from app.utils.data_loader import load_analysis_data
from perf_diagnostics import log_duration


log_duration("Analyse - imports", PAGE_STARTED_AT)


LOGGER = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 600
MIN_TYPE_OBSERVATIONS = 20
STATUS_LABELS = {0: "Approuvée", 1: "Refusée"}
STATUS_COLORS = {"Approuvée": "#2563EB", "Refusée": "#DC2626"}
FILTER_KEYS = (
    "analysis_period",
    "analysis_status",
    "analysis_types",
    "analysis_project",
    "analysis_billable",
)
DAY_LABELS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Chargement de l’analyse…")
def load_cached_analysis_data() -> pd.DataFrame:
    """Charge les données analytiques anonymes depuis PostgreSQL."""
    from app.utils.db_resources import get_database_engine

    return load_analysis_data(engine=get_database_engine())


def reset_filters() -> None:
    """Rétablit les filtres de cette page uniquement."""
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def format_euro(value: float) -> str:
    """Formate un montant selon une présentation française."""
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def format_count(value: int) -> str:
    """Formate un effectif avec des espaces pour les milliers."""
    return f"{value:,}".replace(",", " ")


def aggregate_dimension(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Calcule les agrégats communs aux analyses facturable et projet."""
    summary = (
        frame.groupby(dimension, observed=True)
        .agg(
            expense_count=("target", "size"),
            total_amount=("amount_ttc", "sum"),
            refusal_rate=("target", "mean"),
        )
        .reset_index()
    )
    summary["refusal_rate"] *= 100
    summary["label"] = summary.apply(
        lambda row: (
            f"n = {format_count(int(row['expense_count']))} · "
            f"{row['refusal_rate']:.1f} % refus"
        ),
        axis=1,
    )
    return summary


st.title("Analyse des données")
st.caption(
    "Explorez en détail les dépenses historiques à partir des tables PostgreSQL "
    "normalisées. Les filtres s’appliquent à tous les onglets."
)

data_started_at = perf_counter()
try:
    expenses = load_cached_analysis_data()
except Exception as exc:
    LOGGER.exception("Échec du chargement des données d’analyse", exc_info=exc)
    st.error(
        "Les données d’analyse sont momentanément indisponibles. "
        "Vérifiez la connexion PostgreSQL puis réessayez."
    )
    st.stop()
log_duration("Analyse - données PostgreSQL", data_started_at)

required_columns = {
    "expense_date",
    "expense_type",
    "amount_ttc",
    "billable",
    "project_status",
    "_project_key",
    "target",
}
if expenses.empty:
    st.error("Aucune dépense n’est disponible pour l’analyse.")
    st.stop()
if not required_columns.issubset(expenses.columns):
    st.error("Les données chargées ne respectent pas le schéma analytique attendu.")
    st.stop()
if expenses["expense_date"].isna().any() or not set(
    expenses["target"].dropna().astype(int).unique()
).issubset(STATUS_LABELS):
    st.error("Certaines dates ou valeurs de statut empêchent l’analyse.")
    st.stop()

expenses = expenses.copy()
expenses["status"] = expenses["target"].astype(int).map(STATUS_LABELS)
min_date = expenses["expense_date"].min().date()
max_date = expenses["expense_date"].max().date()
all_statuses = list(STATUS_LABELS.values())
all_types = sorted(expenses["expense_type"].dropna().astype(str).unique().tolist())

with st.sidebar:
    st.header("Filtres de l’analyse")
    st.button("Réinitialiser les filtres", on_click=reset_filters, width="stretch")
    selected_period = st.date_input(
        "Période",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="analysis_period",
    )
    selected_statuses = st.multiselect(
        "Statut",
        options=all_statuses,
        default=all_statuses,
        key="analysis_status",
    )
    selected_types = st.multiselect(
        "Type de dépense",
        options=all_types,
        default=[],
        help="Laisser vide pour inclure tous les types.",
        key="analysis_types",
    )
    selected_project = st.selectbox(
        "Projet",
        options=("Tous", "Avec projet", "Sans projet"),
        help="Les codes projets réels ne sont pas affichés.",
        key="analysis_project",
    )
    selected_billable = st.selectbox(
        "Facturable",
        options=("Tous", "Oui", "Non"),
        key="analysis_billable",
    )

if isinstance(selected_period, (tuple, list)) and len(selected_period) == 2:
    start_date, end_date = selected_period
elif isinstance(selected_period, (tuple, list)) and len(selected_period) == 1:
    start_date = end_date = selected_period[0]
else:
    start_date = end_date = selected_period

filtered = expenses[
    expenses["expense_date"].dt.date.between(start_date, end_date)
].copy()
filtered = filtered[filtered["status"].isin(selected_statuses)]
if selected_types:
    filtered = filtered[filtered["expense_type"].isin(selected_types)]
if selected_project != "Tous":
    filtered = filtered[filtered["project_status"].eq(selected_project)]
if selected_billable != "Tous":
    filtered = filtered[filtered["billable"].eq(selected_billable == "Oui")]

if filtered.empty:
    st.warning("Aucune dépense ne correspond à la combinaison de filtres choisie.")
    st.stop()

general_tab, amounts_tab, types_tab, time_tab, project_tab = st.tabs(
    (
        "Vue générale",
        "Montants",
        "Types",
        "Temps",
        "Facturable / Projet",
    )
)

with general_tab:
    row_count = len(filtered)
    refusal_count = int(filtered["target"].eq(1).sum())
    metrics = (
        ("Nombre de lignes", format_count(row_count)),
        ("Montant TTC total", format_euro(float(filtered["amount_ttc"].sum()))),
        ("Montant TTC moyen", format_euro(float(filtered["amount_ttc"].mean()))),
        ("Montant TTC médian", format_euro(float(filtered["amount_ttc"].median()))),
        ("Nombre de refus", format_count(refusal_count)),
        ("Taux de refus", f"{filtered['target'].eq(1).mean() * 100:.1f} %"),
        ("Types de dépenses", format_count(filtered["expense_type"].nunique())),
        (
            "Nombre de projets",
            format_count(filtered.loc[filtered["_project_key"] >= 0, "_project_key"].nunique()),
        ),
    )
    for offset in (0, 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, metrics[offset : offset + 4]):
            column.metric(label, value)
    st.caption(
        "La dimension projet est volontairement limitée à « avec projet » ou "
        "« sans projet » afin de ne pas exposer les codes projets réels."
    )

with amounts_tab:
    amount_columns = st.columns(2)
    histogram = px.histogram(
        filtered,
        x="amount_ttc",
        nbins=60,
        labels={"amount_ttc": "Montant TTC (€)"},
        title="Distribution des montants TTC",
    )
    histogram.update_traces(marker_color="#2563EB")
    histogram.update_yaxes(title="Nombre de lignes")
    amount_columns[0].plotly_chart(histogram, width="stretch")

    boxplot = px.box(
        filtered,
        x="status",
        y="amount_ttc",
        color="status",
        points="outliers",
        color_discrete_map=STATUS_COLORS,
        labels={"status": "Statut", "amount_ttc": "Montant TTC (€)"},
        title="Montants TTC par statut",
    )
    boxplot.update_layout(showlegend=False)
    amount_columns[1].plotly_chart(boxplot, width="stretch")
    st.caption("Les valeurs extrêmes sont conservées dans les deux graphiques.")

    mean_column, median_column = st.columns(2)
    mean_column.metric("Moyenne", format_euro(float(filtered["amount_ttc"].mean())))
    median_column.metric(
        "Médiane", format_euro(float(filtered["amount_ttc"].median()))
    )
    status_amounts = (
        filtered.groupby("status", observed=True)
        .agg(moyenne=("amount_ttc", "mean"), médiane=("amount_ttc", "median"))
        .reset_index()
        .melt(id_vars="status", var_name="indicateur", value_name="montant")
    )
    comparison = px.bar(
        status_amounts,
        x="status",
        y="montant",
        color="indicateur",
        barmode="group",
        labels={
            "status": "Statut",
            "montant": "Montant TTC (€)",
            "indicateur": "Indicateur",
        },
        title="Moyenne et médiane : approuvées vs refusées",
        color_discrete_sequence=["#2563EB", "#0F766E"],
    )
    st.plotly_chart(comparison, width="stretch")

with types_tab:
    type_summary = (
        filtered.groupby("expense_type", observed=True)
        .agg(
            expense_count=("target", "size"),
            total_amount=("amount_ttc", "sum"),
            refusal_count=("target", "sum"),
            refusal_rate=("target", "mean"),
        )
        .reset_index()
    )
    type_summary["refusal_rate"] *= 100
    type_columns = st.columns(2)
    type_volume = type_summary.nlargest(20, "expense_count").sort_values(
        "expense_count"
    )
    volume_figure = px.bar(
        type_volume,
        x="expense_count",
        y="expense_type",
        orientation="h",
        labels={"expense_count": "Nombre de lignes", "expense_type": "Type"},
        title="Volume par type — 20 premiers",
    )
    volume_figure.update_traces(marker_color="#2563EB")
    type_columns[0].plotly_chart(volume_figure, width="stretch")

    type_amount = type_summary.nlargest(20, "total_amount").sort_values(
        "total_amount"
    )
    amount_figure = px.bar(
        type_amount,
        x="total_amount",
        y="expense_type",
        orientation="h",
        labels={"total_amount": "Montant TTC total (€)", "expense_type": "Type"},
        title="Montant total par type — 20 premiers",
    )
    amount_figure.update_traces(marker_color="#0F766E")
    type_columns[1].plotly_chart(amount_figure, width="stretch")

    reliable_rates = type_summary[
        type_summary["expense_count"] >= MIN_TYPE_OBSERVATIONS
    ].copy()
    st.subheader("Taux de refus par type")
    st.caption(
        "Seuls les types comptant au moins 20 observations dans le périmètre "
        "filtré sont affichés. L’effectif accompagne toujours le taux."
    )
    if reliable_rates.empty:
        st.info("Aucun type n’atteint le minimum de 20 observations.")
    else:
        reliable_rates["label"] = reliable_rates.apply(
            lambda row: (
                f"{row['refusal_rate']:.1f} % "
                f"(n = {format_count(int(row['expense_count']))})"
            ),
            axis=1,
        )
        reliable_rates = reliable_rates.sort_values("refusal_rate")
        rates_figure = px.bar(
            reliable_rates,
            x="refusal_rate",
            y="expense_type",
            orientation="h",
            text="label",
            labels={"refusal_rate": "Taux de refus (%)", "expense_type": "Type"},
        )
        rates_figure.update_traces(marker_color="#DC2626", textposition="outside")
        st.plotly_chart(rates_figure, width="stretch")

    aggregate_export = type_summary.rename(
        columns={
            "expense_type": "Type de dépense",
            "expense_count": "Nombre de lignes",
            "total_amount": "Montant TTC total (€)",
            "refusal_count": "Nombre de refus",
            "refusal_rate": "Taux de refus (%)",
        }
    ).sort_values("Nombre de lignes", ascending=False)
    aggregate_export["Montant TTC total (€)"] = aggregate_export[
        "Montant TTC total (€)"
    ].round(2)
    aggregate_export["Taux de refus (%)"] = aggregate_export[
        "Taux de refus (%)"
    ].round(2)
    aggregate_export["Taux de refus (%)"] = aggregate_export[
        "Taux de refus (%)"
    ].where(aggregate_export["Nombre de lignes"] >= MIN_TYPE_OBSERVATIONS)
    with st.expander("Consulter et télécharger le tableau agrégé"):
        st.caption(
            "Le taux de refus reste vide lorsqu’un type compte moins de 20 "
            "observations ; l’effectif est conservé dans le tableau."
        )
        st.dataframe(aggregate_export, hide_index=True, width="stretch")
        st.download_button(
            "Télécharger l’agrégat par type (CSV)",
            data=aggregate_export.to_csv(index=False).encode("utf-8-sig"),
            file_name="expenseai_analyse_par_type.csv",
            mime="text/csv",
        )

with time_tab:
    monthly = (
        filtered.assign(
            month=filtered["expense_date"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby("month", as_index=False)
        .agg(
            expense_count=("target", "size"),
            total_amount=("amount_ttc", "sum"),
            refusal_rate=("target", "mean"),
        )
    )
    monthly["refusal_rate"] *= 100
    time_columns = st.columns(2)
    monthly_volume = px.line(
        monthly,
        x="month",
        y="expense_count",
        markers=True,
        labels={"month": "Mois", "expense_count": "Nombre de lignes"},
        title="Évolution mensuelle du volume",
    )
    monthly_volume.update_traces(line_color="#2563EB")
    time_columns[0].plotly_chart(monthly_volume, width="stretch")
    monthly_amount = px.line(
        monthly,
        x="month",
        y="total_amount",
        markers=True,
        labels={"month": "Mois", "total_amount": "Montant TTC total (€)"},
        title="Évolution mensuelle du montant",
    )
    monthly_amount.update_traces(line_color="#0F766E")
    time_columns[1].plotly_chart(monthly_amount, width="stretch")

    monthly_rate = px.line(
        monthly,
        x="month",
        y="refusal_rate",
        markers=True,
        labels={"month": "Mois", "refusal_rate": "Taux de refus (%)"},
        title="Évolution mensuelle du taux de refus",
    )
    monthly_rate.update_traces(line_color="#DC2626")
    st.plotly_chart(monthly_rate, width="stretch")

    weekday = (
        filtered.assign(day_number=filtered["expense_date"].dt.dayofweek)
        .groupby("day_number", as_index=False)
        .agg(expense_count=("target", "size"), refusal_rate=("target", "mean"))
    )
    weekday["refusal_rate"] *= 100
    weekday["day"] = weekday["day_number"].map(DAY_LABELS)
    weekday["day"] = pd.Categorical(
        weekday["day"], categories=list(DAY_LABELS.values()), ordered=True
    )
    weekday = weekday.sort_values("day")
    weekday_columns = st.columns(2)
    weekday_volume = px.bar(
        weekday,
        x="day",
        y="expense_count",
        labels={"day": "Jour de la semaine", "expense_count": "Nombre de lignes"},
        title="Volume par jour de semaine",
    )
    weekday_volume.update_traces(marker_color="#2563EB")
    weekday_columns[0].plotly_chart(weekday_volume, width="stretch")
    weekday_rate = px.bar(
        weekday,
        x="day",
        y="refusal_rate",
        labels={"day": "Jour de la semaine", "refusal_rate": "Taux de refus (%)"},
        title="Taux de refus par jour de semaine",
    )
    weekday_rate.update_traces(marker_color="#DC2626")
    weekday_columns[1].plotly_chart(weekday_rate, width="stretch")

    if start_date == min_date and end_date == max_date:
        st.info(
            "Juillet 2025 et juillet 2026 sont des mois partiels dans le jeu de "
            "données ; leurs volumes ne sont pas directement comparables à ceux "
            "des mois complets."
        )

with project_tab:
    comparison_data = filtered.assign(
        facturable=filtered["billable"].map({True: "Facturable", False: "Non facturable"})
    )
    billable_summary = aggregate_dimension(comparison_data, "facturable")
    project_summary = aggregate_dimension(comparison_data, "project_status")

    comparison_columns = st.columns(2)
    billable_figure = px.bar(
        billable_summary,
        x="facturable",
        y="expense_count",
        text="label",
        color="facturable",
        color_discrete_map={"Facturable": "#0F766E", "Non facturable": "#64748B"},
        labels={"facturable": "", "expense_count": "Nombre de lignes"},
        title="Facturable vs non facturable",
    )
    billable_figure.update_layout(showlegend=False)
    billable_figure.update_traces(textposition="outside")
    comparison_columns[0].plotly_chart(billable_figure, w