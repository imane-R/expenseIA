"""Point d'entrée principal de l'application ExpenseAI."""

import streamlit as st


st.set_page_config(
    page_title="ExpenseAI",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)


pages = {
    "ExpenseAI": [
        st.Page("app/app.py", title="Accueil", icon="🏠", default=True),
        st.Page("app/pages/1_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page(
            "app/pages/2_Analyse_des_donnees.py",
            title="Analyse des données",
            icon="🔎",
        ),
        st.Page("app/pages/3_Prediction_IA.py", title="Prédiction", icon="🤖"),
        st.Page("app/pages/4_Historique.py", title="Historique", icon="🕘"),
        st.Page("app/pages/5_A_propos.py", title="À propos", icon="ℹ️"),
    ]
}

navigation = st.navigation(pages)
navigation.run()
