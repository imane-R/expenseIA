"""Diagnostic de performance activable sans sortie dans l'interface."""

from __future__ import annotations

import os
from time import perf_counter


PERF_ENV_VAR = "EXPENSEAI_PERF_DEBUG"


def is_perf_enabled() -> bool:
    """Indique si les mesures terminal sont explicitement activées."""
    return os.getenv(PERF_ENV_VAR, "0").strip().lower() in {"1", "true", "yes"}


def log_duration(label: str, started_at: float) -> float:
    """Écrit une durée dans le terminal et retourne sa valeur en secondes."""
    elapsed = perf_counter() - started_at
    if is_perf_enabled():
        print(f"[PERF] {label}: {elapsed:.3f} s", flush=True)
    return elapsed
