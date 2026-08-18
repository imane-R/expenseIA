"""Simulation du risque de refus d'une ligne de dépense."""

from __future__ import annotations

from datetime import date
import logging

import pandas as pd
import streamlit as st

from app.utils.prediction_service import (
    WITHOUT_PROJECT_LABEL,
    build_expense_data,
    submit_prediction,
)
from database.prediction_repository import (
    load_prediction_options,
    load_recent_predictions,
)
from ml.model_metadata import load_model_metadata


LOGGER = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 600


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Chargement des référentiels…")
def load_form_options() -> dict[str, list[object]]:
    """Charge les types, projets et taux réellement présents dans PostgreSQL."""
    return load_prediction_options()


@st.cache_data(ttl=60, show_spinner=False)
def load_recent_history() -> list[dict[str, object]]:
    """Charge un historique anonyme et volontairement limité."""
    return load_recent_predictions(limit=10)


def format_tax_rate(tax_rate: float) -> str:
    """Affiche une fraction PostgreSQL sous forme de pourcentage lisible."""
    return f"{tax_rate * 100:.2f} %".replace(".", ",")


def format_percentage(value: float) -> str:
    """Formate une probabilité sans changer sa valeur."""
    return f"{value * 100:.1f} %".replace(".", ",")


st.title("Prédiction d'une dépense")
st.write(
    "ExpenseAI estime le risque qu'une ligne de dépense soit refusée à partir "
    "de ses caractéristiques. Le résultat constitue une aide à la décision et "
    "ne remplace pas la validation humaine."
)

try:
    metadata = load_model_metadata()
except Exception as exc:
    LOGGER.exception("Métadonnées ML indisponibles", exc_info=exc)
    st.error("Le modèle ExpenseAI n'est pas disponible.")
    st.stop()

try:
    options = load_form_options()
except Exception as exc:
    LOGGER.exception("Référentiels PostgreSQL indisponibles", exc_info=exc)
    st.error(
        "Les listes de types, projets et taux de taxe sont momentanément "
        "indisponibles. Vérifiez la connexion PostgreSQL puis réessayez."
    )
    st.stop()

expense_types = [str(value) for value in options["expense_types"]]
project_options = [WITHOUT_PROJECT_LABEL, *map(str, options["projects"])]
tax_rates = [float(value) for value in options["tax_rates"]]
if not expense_types or not tax_rates:
    st.error("Les référentiels PostgreSQL sont incomplets pour réaliser une analyse.")
    st.stop()

with st.form("expense_prediction_form", clear_on_submit=False):
    left_column, right_column = st.columns(2)
    with left_column:
        selected_date = st.date_input(
            "Date de la dépense",
            value=date.today(),
        )
        selected_type = st.selectbox(
            "Type de dépense",
            options=expense_types,
        )
        amount_ttc = st.number_input(
            "Montant TTC (€)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.2f",
        )
    with right_column:
        billable_label = st.selectbox("Facturable", options=("Non", "Oui"))
        selected_project = st.selectbox("Projet", options=project_options)
        selected_tax_rate = st.selectbox(
            "Taux de taxe",
            options=tax_rates,
            format_func=format_tax_rate,
            help=(
                "Le pourcentage affiché est transmis au modèle sous sa forme "
                "décimale, par exemple 20 % devient 0,20."
            ),
        )

    submitted = st.form_submit_button(
        "Analyser la dépense",
        type="primary",
        width="stretch",
    )

if submitted:
    try:
        expense_data = build_expense_data(
            expense_date=selected_date,
            expense_type=selected_type,
            amount_ttc=amount_ttc,
            billable=billable_label == "Oui",
            project_selection=selected_project,
            tax_rate=selected_tax_rate,
        )
        submission = submit_prediction(expense_data)
    except FileNotFoundError:
        st.error("Le modèle ExpenseAI n'est pas disponible.")
    except Exception as exc:
        LOGGER.exception("Prédiction ExpenseAI impossible", exc_info=exc)
        st.error(
            "La dépense n'a pas pu être analysée. Vérifiez les informations "
            "saisies puis réessayez."
        )
    else:
        st.session_state["last_expenseai_prediction"] = {
            "prediction": submission.prediction,
            "history_saved": submission.history_id is not None,
        }
        if submission.history_id is not None:
            load_recent_history.clear()
        else:
            LOGGER.warning(
                "Prédiction calculée mais historique non enregistré (%s)",
                type(submission.history_error).__name__,
            )

last_submission = st.session_state.get("last_expenseai_prediction")
if last_submission:
    result = last_submission["prediction"]
    probability = float(result.get("probability", result.get("risk_score", 0.0)))
    threshold = float(result["threshold"])
    predicted_target = int(result["predicted_target"])

    st.divider()
    st.subheader("Résultat de l'analyse")
    if predicted_target == 1:
        st.warning("Dépense à examiner")
        st.write(
            "Le modèle identifie cette dépense comme nécessitant une attention "
            "particulière avant validation."
        )
    else:
        st.success("Risque de refus non signalé")
        st.write(
            "Le modèle ne signale pas cette dépense comme prioritaire pour "
            "contrôle. La décision finale reste à la charge du valideur."
        )

    st.metric("Probabilité estimée de refus", format_percentage(probability))
    st.progress(
        min(max(probability, 0.0), 1.0),
        text=f"Probabilité estimée : {format_percentage(probability)}",
    )
    st.caption(
        "Le seuil de décision est volontairement bas car il privilégie la "
        f"détection des refus. Un dépassement de {format_percentage(threshold)} "
        "ne constitue pas une forte probabilité absolue ni une décision automatique."
    )

    if last_submission["history_saved"]:
        st.caption("Cette simulation a été ajoutée à l'historique PostgreSQL.")
    else:
        st.warning(
            "La prédiction a réussi, mais son historique n'a pas pu être enregistré."
        )

    with st.expander("Détails du modèle"):
        detail_columns = st.columns(2)
        detail_columns[0].metric(
            "Probabilité estimée",
            format_percentage(probability),
        )
        detail_columns[1].metric("Seuil de décision", format_percentage(threshold))
        st.write(f"**Version du modèle :** {result['model_version']}")
        st.write(f"**Calibration :** {result['calibration']}")

with st.expander("Comment fonctionne ExpenseAI ?"):
    st.write(
        "ExpenseAI utilise un modèle de régression logistique entraîné sur "
        "l'historique des dépenses approuvées et refusées."
    )
    st.write(
        "Le modèle a été calibré afin d'améliorer l'interprétation des "
        "probabilités. Le seuil a été déterminé sur les données d'entraînement "
        "en donnant davantage d'importance à la détection des refus."
    )
    st.write(
        "Le résultat aide à prioriser les contrôles et ne constitue jamais une "
        "décision automatique."
    )

with st.expander("Performance du modèle sur le jeu de test"):
    test_metrics = metadata["test_metrics"]
    confusion = metadata["confusion_matrix"]
    performance_columns = st.columns(4)
    performance_columns[0].metric(
        "Recall refus",
        format_percentage(float(test_metrics["recall_refusee"])),
    )
    performance_columns[1].metric(
        "Precision refus",
        format_percentage(float(test_metrics["precision_refusee"])),
    )
    performance_columns[2].metric(
        "ROC-AUC",
        f"{float(test_metrics['roc_auc']):.4f}",
    )
    performance_columns[3].metric(
        "PR-AUC",
        f"{float(test_metrics['average_precision']):.4f}",
    )
    st.write(
        f"Sur le test de référence : **{int(confusion['tp'])} refus détectés**, "
        f"**{int(confusion['fp'])} fausses alertes** et "
        f"**{int(confusion['fn'])} refus non détectés**."
    )
    st.caption(
        "Ces résultats portent sur seulement 23 refus et doivent être interprétés "
        "avec prudence. Ils sont lus depuis les métadonnées du modèle."
    )

st.subheader("Historique récent des analyses")
try:
    history_rows = load_recent_history()
except Exception as exc:
    LOGGER.warning("Historique PostgreSQL indisponible (%s)", type(exc).__name__)
    st.info("L'historique récent est momentanément indisponible.")
else:
    if not history_rows:
        st.info("Aucune analyse manuelle n'a encore été enregistrée.")
    else:
        history = pd.DataFrame(history_rows)
        history["Résultat"] = history["predicted_target"].map(
            {0: "Risque non signalé", 1: "À examiner"}
        )
        history["Probabilité estimée"] = history["probability"].map(
            lambda value: format_percentage(float(value))
        )
        history["Date"] = pd.to_datetime(history["created_at"]).dt.strftime(
            "%d/%m/%Y %H:%M"
        )
        history = history.rename(columns={"model_version": "Version"})
        st.dataframe(
            history[["Date", "Résultat", "Probabilité estimée", "Version"]],
            hide_index=True,
            width="stretch",
        )
