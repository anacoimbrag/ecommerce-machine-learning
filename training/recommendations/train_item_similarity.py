"""Cosine similarity produto x produto para a vitrine personalizada."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.db import connect, fetch_dicts, replace_table  # noqa: E402
from common.plotting import save_figure  # noqa: E402

TOP_K = int(os.environ.get("SIMILARITY_TOP_K", "10"))
HEATMAP_MAX_PRODUCTS = int(os.environ.get("SIMILARITY_HEATMAP_MAX_PRODUCTS", "40"))


def plot_similarity_distribution(rows: list[tuple], trained_at: datetime) -> None:
    scores = [row[2] for row in rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(scores, bins=30, color="steelblue", edgecolor="white")
    ax.set_xlabel("Similarity score")
    ax.set_ylabel("Frequência")
    ax.set_title(f"Distribuição de similaridade produto-produto (top-{TOP_K})")
    save_figure(fig, "train_item_similarity", "similarity_distribution", trained_at)


def plot_similarity_heatmap(
    similarity: np.ndarray, product_ids: list[str], trained_at: datetime
) -> None:
    """Heatmap da matriz de similaridade. Recorta pros produtos mais conectados
    quando o catálogo é grande demais pra caber legível num único gráfico."""
    n = len(product_ids)
    if n > HEATMAP_MAX_PRODUCTS:
        strength = similarity.sum(axis=1)
        top_idx = np.argsort(-strength)[:HEATMAP_MAX_PRODUCTS]
        matrix = similarity[np.ix_(top_idx, top_idx)]
        labels = [product_ids[i] for i in top_idx]
        subtitle = f"top {HEATMAP_MAX_PRODUCTS} de {n} produtos, por força de similaridade"
    else:
        matrix = similarity
        labels = product_ids
        subtitle = f"{n} produtos"

    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.set_yticklabels(labels, fontsize=6)
    ax.set_title(f"Matriz de similaridade produto x produto\n({subtitle})", fontsize=11)
    fig.colorbar(im, ax=ax, label="Similarity score", fraction=0.046, pad=0.04)
    save_figure(fig, "train_item_similarity", "similarity_heatmap", trained_at)


def build_product_similarity_matrix(interactions: list[dict]) -> tuple[np.ndarray, list[str]]:
    customer_ids = sorted({row["customer_id"] for row in interactions})
    product_ids = sorted({row["product_id"] for row in interactions})
    customer_index = {customer_id: i for i, customer_id in enumerate(customer_ids)}
    product_index = {product_id: i for i, product_id in enumerate(product_ids)}

    weights = [row["interaction_weight"] for row in interactions]
    customer_rows = [customer_index[row["customer_id"]] for row in interactions]
    product_cols = [product_index[row["product_id"]] for row in interactions]
    interaction_matrix = csr_matrix(
        (weights, (customer_rows, product_cols)),
        shape=(len(customer_ids), len(product_ids)),
    )

    similarity = cosine_similarity(interaction_matrix.T, dense_output=True)
    np.fill_diagonal(similarity, 0.0)
    return similarity, product_ids


def top_similar_products(
    similarity: np.ndarray, product_ids: list[str], trained_at: datetime
) -> list[tuple]:
    rows = []
    for i, product_id in enumerate(product_ids):
        neighbor_indices = np.argsort(-similarity[i])[:TOP_K]
        for j in neighbor_indices:
            score = float(similarity[i, j])
            if score > 0:
                rows.append((product_id, product_ids[j], score, trained_at))
    return rows


def main() -> int:
    con = connect()
    interactions = fetch_dicts(con, """
        SELECT customer_id, product_id, interaction_weight
        FROM feature.feat_customer_product_interactions
    """)
    if not interactions:
        print("feat_customer_product_interactions está vazia — nada a treinar.", file=sys.stderr)
        return 1

    similarity, product_ids = build_product_similarity_matrix(interactions)
    trained_at = datetime.now(timezone.utc)
    rows = top_similar_products(similarity, product_ids, trained_at)
    plot_similarity_distribution(rows, trained_at)
    plot_similarity_heatmap(similarity, product_ids, trained_at)

    replace_table(
        con, "raw.product_similarity",
        {"product_id_a": "VARCHAR", "product_id_b": "VARCHAR",
         "similarity_score": "DOUBLE", "trained_at": "TIMESTAMP"},
        rows,
    )
    print(f"raw.product_similarity: {len(rows)} linhas "
          f"({len(product_ids)} produtos, top-{TOP_K} vizinhos cada).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
