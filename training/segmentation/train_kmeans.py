"""K-Means sobre RFM para clusterização dinâmica de clientes."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# permite `from common.db import ...` quando o script roda direto (python training/segmentation/train_kmeans.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.db import connect, fetch_dicts, replace_table  # noqa: E402
from common.plotting import save_figure  # noqa: E402

K_MIN = int(os.environ.get("KMEANS_K_MIN", "3"))
K_MAX = int(os.environ.get("KMEANS_K_MAX", "8"))
RANDOM_STATE = 42


def pick_best_k(
    features: np.ndarray, k_min: int, k_max: int
) -> tuple[int, dict[int, float], dict[int, np.ndarray]]:
    silhouette_by_k = {}
    labels_by_k = {}
    for k in range(k_min, k_max + 1):
        labels = KMeans(n_clusters=k, init="k-means++", n_init=10).fit_predict(features)
        silhouette_by_k[k] = silhouette_score(features, labels)
        labels_by_k[k] = labels
        print(f"k={k}: silhouette={silhouette_by_k[k]:.4f}", flush=True)
    best_k = max(silhouette_by_k, key=silhouette_by_k.get)
    return best_k, silhouette_by_k, labels_by_k


def plot_silhouette_scores(silhouette_by_k: dict[int, float], best_k: int, trained_at: datetime) -> None:
    ks = sorted(silhouette_by_k)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ks, [silhouette_by_k[k] for k in ks], marker="o")
    ax.axvline(best_k, color="red", linestyle="--", label=f"k escolhido = {best_k}")
    ax.set_xlabel("k (número de clusters)")
    ax.set_ylabel("Silhouette score")
    ax.set_title("K-Means RFM: silhouette score por k")
    ax.legend()
    save_figure(fig, "train_kmeans", "silhouette", trained_at)


def plot_clusters(rfm: np.ndarray, clusters: np.ndarray, k: int, trained_at: datetime) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    scatter = ax.scatter(rfm[:, 0], rfm[:, 2], c=clusters, cmap="tab10", alpha=0.6)
    ax.set_xlabel("Recency (dias)")
    ax.set_ylabel("Net revenue")
    ax.set_title(f"K-Means RFM: clusters de clientes (k={k})")
    ax.add_artist(ax.legend(*scatter.legend_elements(), title="Cluster"))
    save_figure(fig, "train_kmeans", f"clusters_k{k}", trained_at)


def main() -> int:
    con = connect()
    customers = fetch_dicts(con, """
        SELECT customer_id, recency_days, total_orders, net_revenue
        FROM feature.feat_rfm_features
        WHERE has_purchase_history
    """)
    if not customers:
        print("Nenhum cliente com histórico de compra em feat_rfm_features.", file=sys.stderr)
        return 1

    rfm = np.array([[c["recency_days"], c["total_orders"], c["net_revenue"]] for c in customers])
    rfm_scaled = StandardScaler().fit_transform(rfm)

    max_testable_k = min(K_MAX, len(customers) - 1)
    silhouette_by_k = labels_by_k = None
    if max_testable_k >= K_MIN:
        k, silhouette_by_k, labels_by_k = pick_best_k(rfm_scaled, K_MIN, max_testable_k)
        clusters = labels_by_k[k]
    else:
        k = max(2, max_testable_k)
        clusters = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit_predict(rfm_scaled)
        print(f"Poucos clientes ({len(customers)}); usando k={k} sem otimizar silhouette.",
              file=sys.stderr)

    trained_at = datetime.now(timezone.utc)
    if silhouette_by_k:
        plot_silhouette_scores(silhouette_by_k, k, trained_at)
    if labels_by_k:
        # Um scatter por k testado (não só o escolhido), pra dar pra inspecionar
        # se um k vizinho separa melhor algum subgrupo visível só na projeção 2D.
        for candidate_k, candidate_labels in labels_by_k.items():
            plot_clusters(rfm, candidate_labels, candidate_k, trained_at)
    else:
        plot_clusters(rfm, clusters, k, trained_at)

    rows = [
        (customer["customer_id"], int(cluster_id), trained_at)
        for customer, cluster_id in zip(customers, clusters)
    ]
    replace_table(
        con, "raw.customer_clusters",
        {"customer_id": "VARCHAR", "cluster_id": "INTEGER", "trained_at": "TIMESTAMP"},
        rows,
    )
    print(f"raw.customer_clusters: {len(rows)} linhas, k={k}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
