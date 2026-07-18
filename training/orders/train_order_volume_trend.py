"""Gradient Boosting sobre volume de pedidos diário: tendência (histórico + previsão futura).

Mesma abordagem autoregressiva do train_revenue_trend.py, mas o alvo é o
número de pedidos por dia (order_count) -- sinaliza se o volume de vendas
está subindo, estável ou caindo, independente do ticket médio. Reaproveita
feature.feat_revenue_daily (já tem order_count) em vez de criar uma feature
nova só pra isso.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.db import connect, fetch_dicts, replace_table  # noqa: E402
from common.plotting import save_figure  # noqa: E402

ROLLING_SHORT = 7
ROLLING_LONG = 28
# +-2% de diferença entre previsto e referência vira "alta"/"queda"; dentro disso é "estável".
TREND_THRESHOLD = 0.02
# ROLLING_LONG dias de warm-up pras médias móveis + margem, senão o modelo
# treina em poucos pontos e a tendência fica ruído.
MIN_DAYS = int(os.environ.get("ORDER_VOLUME_TREND_MIN_DAYS", str(ROLLING_LONG + 7)))
# ~3 meses de previsão recursiva além do último dia com dado real.
FORECAST_HORIZON_DAYS = int(os.environ.get("ORDER_VOLUME_TREND_FORECAST_DAYS", "90"))
FEATURE_NAMES = [
    "day_index", "day_of_week", "order_count", "order_count_lag_1",
    "order_count_lag_7", "rolling_mean_7", "rolling_mean_28",
]


def build_features(days: list[dict]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """1 linha por dia (a partir de ROLLING_LONG), prevendo order_count do dia seguinte.

    `aligned_days[j]` é o dia AO QUAL o valor previsto/real se refere (dia i+1),
    não o dia "hoje" (i) cujas features alimentaram a previsão.
    """
    counts = [float(d["order_count"]) for d in days]
    features, targets, aligned_days = [], [], []
    for i in range(ROLLING_LONG, len(days) - 1):
        window_short = counts[i - ROLLING_SHORT + 1: i + 1]
        window_long = counts[i - ROLLING_LONG + 1: i + 1]
        features.append([
            i,
            days[i]["day"].weekday(),
            counts[i],
            counts[i - 1],
            counts[i - 7],
            float(np.mean(window_short)),
            float(np.mean(window_long)),
        ])
        targets.append(counts[i + 1])
        aligned_days.append(days[i + 1])
    return np.array(features), np.array(targets), aligned_days


def forecast_future(
    model: GradientBoostingRegressor, last_day, base_counts: list[float], horizon: int
) -> list[dict]:
    """Previsão recursiva: cada dia previsto entra como histórico do próximo passo."""
    extended = list(base_counts)
    rows = []
    for step in range(1, horizon + 1):
        i = len(extended) - 1
        today_day = last_day + timedelta(days=step - 1)
        window_short = extended[i - ROLLING_SHORT + 1: i + 1]
        window_long = extended[i - ROLLING_LONG + 1: i + 1]
        features = np.array([[
            i,
            today_day.weekday(),
            extended[i],
            extended[i - 1],
            extended[i - 7],
            float(np.mean(window_short)),
            float(np.mean(window_long)),
        ]])
        predicted = float(model.predict(features)[0])
        rows.append({
            "day": last_day + timedelta(days=step),
            "predicted_order_count": predicted,
            "trend_label": classify_trend(extended[i], predicted),
        })
        extended.append(predicted)
    return rows


def classify_trend(reference: float, predicted: float) -> str:
    if reference == 0:
        return "estável"
    change = (predicted - reference) / reference
    if change > TREND_THRESHOLD:
        return "alta"
    if change < -TREND_THRESHOLD:
        return "queda"
    return "estável"


def plot_actual_vs_predicted(
    historical_days: list[dict], actual: np.ndarray, predicted: np.ndarray,
    forecast_rows: list[dict], trained_at: datetime,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    x_hist = [d["day"] for d in historical_days]
    ax.plot(x_hist, actual, label="Pedidos reais", color="steelblue")
    ax.plot(x_hist, predicted, label="Previsto (backtest 1 dia)",
            color="darkorange", linestyle="--", alpha=0.6)

    x_forecast = [row["day"] for row in forecast_rows]
    y_forecast = [row["predicted_order_count"] for row in forecast_rows]
    ax.plot(x_forecast, y_forecast, label=f"Previsão ({len(forecast_rows)} dias)",
            color="firebrick", linestyle="--")
    ax.axvline(x_hist[-1], color="gray", linestyle=":", linewidth=1)

    ax.set_xlabel("Data")
    ax.set_ylabel("Pedidos por dia")
    ax.set_title("Tendência de volume de pedidos: histórico + previsão (Gradient Boosting)")
    ax.legend()
    fig.autofmt_xdate()
    save_figure(fig, "train_order_volume_trend", "actual_vs_predicted", trained_at)


def plot_feature_importance(model: GradientBoostingRegressor, trained_at: datetime) -> None:
    importances = model.feature_importances_
    order = np.argsort(importances)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh([FEATURE_NAMES[i] for i in order], importances[order], color="seagreen")
    ax.set_xlabel("Importância")
    ax.set_title("Gradient Boosting: importância das features (tendência de volume de pedidos)")
    save_figure(fig, "train_order_volume_trend", "feature_importance", trained_at)


def main() -> int:
    con = connect()
    days = fetch_dicts(con, """
        SELECT day, order_count
        FROM feature.feat_revenue_daily
        ORDER BY day
    """)
    if len(days) < MIN_DAYS:
        print(f"feat_revenue_daily tem só {len(days)} dias (mínimo {MIN_DAYS}) — nada a treinar.",
              file=sys.stderr)
        return 1

    features, targets, aligned_days = build_features(days)
    model = GradientBoostingRegressor(random_state=42)
    model.fit(features, targets)
    predicted = model.predict(features)

    mae = mean_absolute_error(targets, predicted)
    r2 = r2_score(targets, predicted)
    print(f"Tendência de volume de pedidos ({len(aligned_days)} dias): "
          f"MAE (in-sample) = {mae:.2f}, R² (in-sample) = {r2:.4f}", flush=True)

    counts = [float(d["order_count"]) for d in days]
    forecast_rows = forecast_future(model, days[-1]["day"], counts, FORECAST_HORIZON_DAYS)
    print(f"Previsão futura: {len(forecast_rows)} dias além de {days[-1]['day']}.", flush=True)

    trained_at = datetime.now(timezone.utc)
    plot_actual_vs_predicted(aligned_days, targets, predicted, forecast_rows, trained_at)
    plot_feature_importance(model, trained_at)

    result_rows = [
        (datetime.combine(day["day"], datetime.min.time()), float(actual), float(pred),
         classify_trend(actual, pred), False, trained_at)
        for day, actual, pred in zip(aligned_days, targets, predicted)
    ] + [
        (datetime.combine(row["day"], datetime.min.time()), None,
         float(row["predicted_order_count"]), row["trend_label"], True, trained_at)
        for row in forecast_rows
    ]
    replace_table(
        con, "raw.order_volume_trend_forecast",
        {"day": "TIMESTAMP", "actual_order_count": "Nullable(Float64)",
         "predicted_order_count": "DOUBLE", "trend_label": "VARCHAR",
         "is_forecast": "BOOLEAN", "trained_at": "TIMESTAMP"},
        result_rows,
        order_by="day",
    )
    print(f"raw.order_volume_trend_forecast: {len(result_rows)} linhas "
          f"({len(aligned_days)} histórico + {len(forecast_rows)} previsão).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
