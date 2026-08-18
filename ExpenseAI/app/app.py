"""Page d'accueil de l'application ExpenseAI."""

import streamlit as st


st.title("ExpenseAI")
st.subheader(
    "Assistant intelligent pour l’analyse et la prédiction des notes de frais"
)

st.markdown(
    """
ExpenseAI est une application d’aide à la décision destinée à faciliter l’analyse
et, à terme, la validation des notes de frais. Elle réunira la visualisation des
données historiques, le suivi des décisions et une prédiction explicable du statut
d’une nouvelle demande.

Cette première version pose les fondations techniques du projet. Le modèle de
Machine Learning sera développé après l’audit, la compréhension et la préparation
des données.
"""
)

st.info("🚧 Application en cours de développement.")
