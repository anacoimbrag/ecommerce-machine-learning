"""Helper para salvar gráficos de cada execução de treino em output/."""

from __future__ import annotations

import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")


def save_figure(fig: plt.Figure, script_name: str, chart_name: str, trained_at: datetime) -> str:
    """Salva `fig` em output/<script_name>_<chart_name>_<timestamp>.png e fecha a figura."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = trained_at.strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUTPUT_DIR, f"{script_name}_{chart_name}_{timestamp}.png")
    fig.savefig(path, bbox_inches="tight", dpi=100)
    plt.close(fig)
    print(f"Gráfico salvo em {path}", flush=True)
    return path
