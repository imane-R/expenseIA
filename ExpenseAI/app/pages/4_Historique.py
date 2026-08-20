"""Historique des résultats produits par ExpenseAI."""

from __future__ import annotations

from time import perf_counter

PAGE_STARTED_AT = perf_counter()

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from database.prediction_repository import load_prediction_history
from perf_diagnostics import log_duration


log_duration("Historique - imports", PAGE_STARTED_AT)


LOGGER = logging.getLogger(__name__)
MAX_HISTORY_ROWS = 500
RESULT_LABELS = {0: "Risque non signalé", 1: "À examiner"}
RESULT_COLORS = {"Risque non signalé": "#2563EB", "À examiner": "#DC2626"}


@st.cache_data(ttl=30, show_spinner="Chargement de l’historique…")
def load_history_data() -> pd.DataFrame:
    """Charge un instantané court, rafraîchissable et sans identifiant."""
    from app.utils.db_resources import get_database_engine

    history = pd.DataFrame(
        load_prediction_history(
            limit=MAX_HISTORY_ROWS,
            engine=get_database_engine(),
        )
    )
    if history.empty:
        return history
    history["created_at"] = pd.to_datetime(history["created_at"], errors="coerce")
    history["predicted_target"] = pd.to_numeric(
        history["predicted_target"], errors="coerce"
    ).astype("Int64")
    history["probability"] = pd.to_numeric(history["probability"], errors="coerce")
    history["model_version"] = (
        history["model_version"].astype("string").fillna("Non renseignée")
    )
    return history


def format_count(value: int) -> str:
    """Formate un effectif avec des espaces pour les milliers."""
    return f"{value:,}".replace(",", " ")


st.title("Historique")
st.caption(
    "Cette page présente uniquement les résultats générés par ExpenseAI. "
    "Ils ne correspondent pas aux décisions réelles des valideurs."
)

if st.button(
    "Actualiser l’historique",
    help="Recharge immédiatement les prédictions enregistrées dans PostgreSQL.",
):
    load_history_data.clear()

data_started_at = perf_counter()
try:
    history = load_history_data()
except Exception as exc:
    LOGGER.exception("Historique PostgreSQL indisponible", exc_info=exc)
    st.error(
        "L’historique est momentanément indisponible. "
        "Vérifiez la connexion PostgreSQL puis réessayez."
    )
    st.stop()
log_duration("Historique - données PostgreSQL", data_started_at)

if history.empty:
    st.info("Aucune analyse n’a encore été enregistrée.")
    st.stop()

required_columns = {
    "created_at",
    "predicted_target",
    "probability",
    "model_version",
}
if not required_columns.issubset(history.columns):
    st.error("L’historique ne respecte pas le schéma attendu.")
    st.stop()
if history["created_at"].isna().any() or history[
    ["predicted_target", "probability"]
].isna().any().any():
    st.error("Certaines prédictions enregistrées ne peuvent pas être affichées.")
    st.stop()
if not set(history["predicted_target"].astype(int).unique()).issubset(RESULT_LABELS):
    st.error("Certaines prédictions enregistrées ont un résultat invalide.")
    st.stop()

history = history.copy()
history["result"] = history["predicted_target"].astype(int).map(RESULT_LABELS)
history = history.sort_values("created_at", ascending=False)
min_date = history["created_at"].min().date()
max_date = history["created_at"].max().date()
all_versions = sorted(history["model_version"].astype(str).unique().tolist())

with st.sidebar:
    st.header("Filtres de l’historique")
    selected_period = st.date_input(
        "Période",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="history_period",
    )
    selected_result = st.selectbox(
        "Résultat",
        options=("Tous", "À examiner", "Risque non signalé"),
        key="history_result",
    )
    selected_versions = st.multiselect(
        "Version du modèle",
        options=all_versions,
        default=all_versions,
        key="history_versions",
    )

if isinstance(selected_period, (tuple, list)) and len(selected_period) == 2:
    start_date, end_date = selected_period
elif isinstance(selected_period, (tuple, list)) and len(selected_period) == 1:
    start_date = end_date = selected_period[0]
else:
    start_date = end_date = selected_period

filtered = history[
    history["created_at"].dt.date.between(start_date, end_date)
].copy()
if selected_result != "Tous":
    filtered = filtered[filtered["result"].eq(selected_result)]
filtered = filtered[filtered["model_version"].isin(selected_versions)]

if filtered.empty:
    st.warning("Aucune prédiction ne correspond aux filtres choisis.")
    st.stop()

total_count = len(filtered)
review_count = int(filtered["predicted_target"].eq(1).sum())
safe_count = int(filtered["predicted_target"].eq(0).sum())
mean_probability = float(filtered["probability"].mean()) * 100

kpi_columns = st.columns(4)
kpi_columns[0].metric("Nombre total d’analyses", format_count(total_count))
kpi_columns[1].metric("À examiner", format_count(review_count))
kpi_columns[2].metric("Risques non signalés", format_count(safe_count))
kpi_columns[3].metric("Probabilité moyenne estimée", f"{mean_probability:.1f} %")

chart_columns = st.columns(2)
daily = (
    filtered.assign(day=filtered["created_at"].dt.floor("D"))
    .groupby("day", as_index=False)
    .size()
    .rename(columns={"size": "prediction_count"})
)
daily_figure = px.bar(
    daily,
    x="day",
    y="prediction_count",
    labels={"day": "Jour", "prediction_count": "Nombre de prédictions"},
    title="Nombre de prédictions par jour",
)
daily_figure.update_traces(marker_color="#2563EB")
chart_columns[0].plotly_chart(daily_figure, width="stretch")

result_summary = filtered.groupby("result", observed=True).size().reset_index(name="count")
result_figure = px.pie(
    result_summary,
    names="result",
    values="count",
    color="result",
    color_discrete_map=RESULT_COLORS,
    hole=0.45,
    title="Répartition des résultats ExpenseAI",
)
result_figure.update_traces(textinfo="percent+value")
chart_columns[1].plotly_chart(result_figure, width="stretch")

st.subheader("Prédictions les plus récentes")
display_limit = st.selectbox(
    "Nombre de lignes à afficher",
    options=(25, 50, 100, 250),
    index=0,
)
display_history = filtered.head(display_limit).copy()
display_history["Date"] = display_history["created_at"].dt.strftime(
    "%d/%m/%Y %H:%M:%S"
)
display_history["Résultat"] = display_history["result"]
display_history["Probabilité estimée de refus"] = (
    display_history["probability"] * 100
)
display_history["Version du modèle"] = display_history["model_version"]
st.dataframe(
    display_history[
        [
            "Date",
            "Résultat",
            "Probabilité estimée de refus",
            "Version du modèle",
        ]
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "Probabilité estimée de refus": st.column_config.ProgressColumn(
            "Probabilité estimée de refus",
            format="%.1f %%",
            min_value=0.0,
            max_value=100.0,
        )
    },
)
st.caption(
    f"{min(display_limit, total_count)} prédiction(s) affichée(s) sur "
    f"{format_count(total_count)}, de la plus récente à la plus ancienne."
)
if len(history) == MAX_HISTORY_ROWS:
    st.info(
        f"L’affichage est limité aux {format_count(MAX_HISTORY_ROWS)} prédictions "
        "les plus récentes afin de préserver les performances."
    )

log_duration("Historique - total", PAGE_STARTED_AT)
