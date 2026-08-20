"""Cache Streamlit commun des métadonnées du modèle."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ml.model_metadata import load_model_metadata


@st.cache_data(ttl=600, show_spinner=False)
def load_model_metadata_cached() -> dict[str, Any]:
    """Lit le JSON une fois pour les pages Prédiction et À propos."""
    return load_model_metadata()
