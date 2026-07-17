"""Regressão logística única (promoção como feature categórica): propensão de conversão do cliente."""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.db import connect, fetch_dicts, replace_table  # noqa: E402
from common.plotting import save_figure  # noqa: E402

MIN_SAMPLES_PER_CAMPAIGN = int(os.environ.get("PROPENSITY_MIN_SAMPLES", "20"))
FEATURE_COLUMNS = [
    "view_count", "select_count", "days_since_last_exposure",
    "recency_days", "has_purchase_history", "total_orders", "net_revenue", "avg_order_value",
]


def plot_propensity_distribution(scores_by_label: dict[int, list[float]], trained_at: datetime) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(scores_by_label[0], bins=30, alpha=0.6, label="Não converteu", color="lightcoral")
    ax.hist(scores_by_label[1], bins=30, alpha=0.6, label="Converteu", color="seagreen")
    ax.set_xlabel("Propensity score")
    ax.set_ylabel("Frequência")
    ax.set_title("Regressão logística: propensity score por conversão real")
    ax.legend()
    save_figure(fig, "train_propensity", "propensity_distribution", trained_at)


def plot_sigmoid_curve(
    logits_by_label: dict[int, list[float]],
    scores_by_label: dict[int, list[float]],
    trained_at: datetime,
) -> None:
    all_logits = logits_by_label[0] + logits_by_label[1]
    z = np.linspace(min(all_logits), max(all_logits), 200)
    curve = 1 / (1 + np.exp(-z))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(z, curve, color="black", linewidth=2, label="sigmoid(z)")
    ax.scatter(logits_by_label[0], scores_by_label[0], alpha=0.3, s=10,
               color="lightcoral", label="Não converteu")
    ax.scatter(logits_by_label[1], scores_by_label[1], alpha=0.3, s=10,
               color="seagreen", label="Converteu")
    ax.axhline(0.5, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("z (combinação linear das features)")
    ax.set_ylabel("P(conversão) = sigmoid(z)")
    ax.set_title("Regressão logística: curva sigmoide")
    ax.legend()
    save_figure(fig, "train_propensity", "sigmoid", trained_at)


def train_propensity_model(
    rows: list[dict], promotion_index: dict[str, int]
) -> tuple[np.ndarray, np.ndarray]:
    numeric = np.array([[float(row[col] or 0) for col in FEATURE_COLUMNS] for row in rows])
    numeric_scaled = StandardScaler().fit_transform(numeric)

    promotion_onehot = np.zeros((len(rows), len(promotion_index)))
    for i, row in enumerate(rows):
        promotion_onehot[i, promotion_index[row["promotion_id"]]] = 1.0
    features = np.hstack([numeric_scaled, promotion_onehot])

    converted = np.array([row["converted"] for row in rows], dtype=int)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(features, converted)
    return model.predict_proba(features)[:, 1], model.decision_function(features)


def main() -> int:
    con = connect()
    exposures = fetch_dicts(con, f"""
        SELECT customer_id, promotion_id, {", ".join(FEATURE_COLUMNS)}, converted
        FROM feature.feat_campaign_training_data
    """)
    if not exposures:
        print("feat_campaign_training_data está vazia — nada a treinar.", file=sys.stderr)
        return 1

    samples_per_promotion = Counter(row["promotion_id"] for row in exposures)
    conversions_per_promotion = Counter(row["promotion_id"] for row in exposures if row["converted"])

    trained_promotions = sorted(
        promo for promo, samples in samples_per_promotion.items()
        if samples >= MIN_SAMPLES_PER_CAMPAIGN
    )
    skipped_promotions = sorted(set(samples_per_promotion) - set(trained_promotions))
    if skipped_promotions:
        print(f"Puladas (poucas amostras): {skipped_promotions}", flush=True)
    for promo in trained_promotions:
        print(f"{promo}: {samples_per_promotion[promo]} amostras, "
              f"{conversions_per_promotion[promo]} conversões.", flush=True)

    training_rows = [row for row in exposures if row["promotion_id"] in trained_promotions]
    if not training_rows:
        print("Nenhuma campanha com amostras suficientes pra treinar.", file=sys.stderr)
        return 1

    promotion_index = {promo: i for i, promo in enumerate(trained_promotions)}
    scores, logits = train_propensity_model(training_rows, promotion_index)

    converted = [row["converted"] for row in training_rows]
    auc = roc_auc_score(converted, scores)
    print(f"Modelo único ({len(trained_promotions)} campanhas, {len(training_rows)} amostras): "
          f"AUC (in-sample) = {auc:.4f}", flush=True)

    trained_at = datetime.now(timezone.utc)
    scores_by_label: dict[int, list[float]] = {0: [], 1: []}
    logits_by_label: dict[int, list[float]] = {0: [], 1: []}
    for row, score, logit in zip(training_rows, scores, logits):
        scores_by_label[row["converted"]].append(float(score))
        logits_by_label[row["converted"]].append(float(logit))
    plot_propensity_distribution(scores_by_label, trained_at)
    plot_sigmoid_curve(logits_by_label, scores_by_label, trained_at)

    result_rows = [
        (row["customer_id"], row["promotion_id"], float(score), trained_at)
        for row, score in zip(training_rows, scores)
    ]
    replace_table(
        con, "raw.campaign_propensity",
        {"customer_id": "VARCHAR", "promotion_id": "VARCHAR",
         "propensity_score": "DOUBLE", "trained_at": "TIMESTAMP"},
        result_rows,
    )
    print(f"raw.campaign_propensity: {len(result_rows)} linhas "
          f"({len(trained_promotions)} campanhas treinadas).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
