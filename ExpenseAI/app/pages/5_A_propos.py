"""Présentation, performances et limites du projet ExpenseAI."""

from __future__ import annotations

from time import perf_counter

PAGE_STARTED_AT = perf_counter()

from datetime import datetime
import logging

import streamlit as st

from app.utils.metadata_resource import load_model_metadata_cached
from perf_diagnostics import log_duration


log_duration("À propos - imports", PAGE_STARTED_AT)


LOGGER = logging.getLogger(__name__)


def format_percentage(value: float) -> str:
    """Formate une proportion comme un pourcentage lisible."""
    return f"{value * 100:.1f} %".replace(".", ",")


def format_creation_date(value: object) -> str:
    """Formate une date ISO issue des métadonnées, sans valeur codée en dur."""
    if not value:
        return "Non renseignée"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return parsed.strftime("%d/%m/%Y à %H:%M UTC")


st.title("À propos")

st.header("ExpenseAI")
st.write(
    "ExpenseAI est une application d'aide à la validation des notes de frais. "
    "Elle analyse les caractéristiques d'une ligne de dépense afin d'estimer "
    "son risque de refus et d'aider les valideurs à prioriser les contrôles."
)
st.info(
    "ExpenseAI fournit une aide à la décision : la validation finale reste "
    "toujours sous la responsabilité d’une personne."
)

st.header("Fonctionnement")
flow_column, explanation_column = st.columns([1, 2])
with flow_column:
    st.markdown(
        """
**Données historiques**

↓

**Nettoyage et préparation**

↓

**Modèle de classification**

↓

**Calibration**

↓

**Estimation du risque**

↓

**Aide à la décision humaine**
"""
    )
with explanation_column:
    st.write(
        "Les dépenses passées permettent d’apprendre des régularités statistiques. "
        "Après préparation, le modèle estime une probabilité de refus. La "
        "calibration améliore l’interprétation de cette probabilité, puis le "
        "résultat sert à prioriser les contrôles, jamais à décider automatiquement."
    )

metadata_started_at = perf_counter()
try:
    metadata = load_model_metadata_cached()
except Exception as exc:
    LOGGER.exception("Métadonnées ExpenseAI indisponibles", exc_info=exc)
    st.error("Les informations du modèle sont momentanément indisponibles.")
    st.stop()
log_duration("À propos - metadata JSON", metadata_started_at)

st.header("Modèle")
model_columns = st.columns(4)
model_columns[0].metric("Type de modèle", str(metadata["model_name"]))
model_columns[1].metric("Version", str(metadata["model_version"]))
model_columns[2].metric("Calibration", str(metadata["calibration"]))
model_columns[3].metric(
    "Date de création", format_creation_date(metadata.get("created_at_utc"))
)
st.caption(
    "Ces informations sont lues directement depuis les métadonnées du modèle "
    "déployé."
)

st.header("Performances")
test_metrics = metadata["test_metrics"]
performance_columns = st.columns(5)
performance_columns[0].metric(
    "Recall refus", format_percentage(float(test_metrics["recall_refusee"]))
)
performance_columns[1].metric(
    "Precision refus", format_percentage(float(test_metrics["precision_refusee"]))
)
performance_columns[2].metric(
    "PR-AUC", f"{float(test_metrics['average_precision']):.4f}"
)
performance_columns[3].metric(
    "ROC-AUC", f"{float(test_metrics['roc_auc']):.4f}"
)
performance_columns[4].metric(
    "Balanced Accuracy", f"{float(test_metrics['balanced_accuracy']):.4f}"
)

st.markdown(
    """
- **Recall refus** : proportion de dépenses réellement refusées que le modèle parvient à signaler.
- **Precision refus** : proportion des dépenses signalées qui sont effectivement refusées.
- **PR-AUC** : qualité du compromis entre précision et détection des refus, particulièrement informative lorsque les refus sont rares.
- **ROC-AUC** : capacité du modèle à classer une dépense refusée au-dessus d’une dépense approuvée sur l’ensemble des seuils.
- **Balanced Accuracy** : moyenne de la capacité à reconnaître chacune des deux classes, sans laisser la classe majoritaire dominer la mesure.
"""
)
st.caption(
    "Ces métriques décrivent les résultats sur le jeu de test de référence. "
    "Elles ne garantissent pas la performance sur chaque nouvelle dépense."
)

st.header("Limites")
st.warning(
    "Le modèle est imparfait et doit être utilisé avec recul, en complément des "
    "règles métier et de l’expertise des valideurs."
)
st.markdown(
    """
- La classe refusée est très minoritaire dans les données disponibles.
- L’historique disponible couvre une période limitée.
- Le modèle peut produire des faux positifs et des faux négatifs.
- Les comportements et les règles de validation peuvent évoluer dans le temps.
- Les performances doivent être surveillées et réévaluées régulièrement.
- Le modèle ne remplace pas un valideur humain.
"""
)

st.header("Technologies")
technology_columns = st.columns(4)
for column, technologies in zip(
    technology_columns,
    (
        ("Python", "PostgreSQL"),
        ("Pandas", "Scikit-learn"),
        ("Streamlit", "Plotly"),
        ("SHAP",),
    ),
):
    for technology in technologies:
        column.markdown(f"- {technology}")

with st.expander("Méthodologie du projet"):
    st.markdown(
        """
1. Audit et contrôle de la qualité des données.
2. Preprocessing et analyse exploratoire (EDA).
3. Split groupé pour limiter les fuites entre apprentissage et évaluation.
4. Validation croisée et comparaiso