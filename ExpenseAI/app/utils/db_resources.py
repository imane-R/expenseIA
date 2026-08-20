"""Ressources PostgreSQL partagées par les pages Streamlit."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine


@st.cache_resource(show_spinner=False)
def get_database_engine() -> Engine:
    """Crée un seul pool SQLAlchemy réutilisable par le processus Streamlit."""
    from database.connection import create_db_engine

    return create_db_engine()
