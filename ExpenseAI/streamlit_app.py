"""Point d'entrée principal de l'application ExpenseAI."""

from time import perf_counter

APP_STARTED_AT = perf_counter()

import streamlit as st

from perf_diagnostics import log_duration


log_duration("Application - import Streamlit", APP_STARTED_AT)


st.set_page_config(
    page_title="ExpenseAI",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)


pages = {
    "ExpenseAI": [
        st.Page("app/app.py", title="Accueil", default=True),
        st.Page("app/pages/1_Dashboard.py", title="Dashboard"),
        st.Page(
            "app/pages/2_Analyse_des_donnees.py",
            title="Analyse des données",
        ),
        st.Page("app/pages/3_Prediction_IA.py", title="Prédiction"),
        st.Page("app/pages/4_Historique.py", title="Historique"),
        st.Page("app/pages/5_A_propos.py", title="À propos"),
    ]
}

navigation = st.navigation(pages)
navigation.run()
