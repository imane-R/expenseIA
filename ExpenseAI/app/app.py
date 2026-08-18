"""Page d'accueil de l'application ExpenseAI."""

import streamlit as st


st.title("ExpenseAI")
st.subheader(
    "Assistant intelligent pour l’analyse et la prédiction des notes de frais"
)

st.markdown(
    """
ExpenseAI est une application d’aide à la décision destinée à faciliter l’analyse
et la validation des notes de frais. Elle réunit la visualisation des données
historiques et l’estimation du risque de refus d’une nouvelle ligne de dépense.

Le modèle contribue à prioriser les contrôles. Il ne remplace jamais la décision
du valideur et ses résultats doivent être interprétés avec prudence.
"""
)

st.info("Utilisez le Dashboard pour explorer l’historique ou la page Prédiction pour analyser une dépense.")
