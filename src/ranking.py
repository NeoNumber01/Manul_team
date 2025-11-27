"""Compute pagerank and risk scores without relying on scipy."""

import numpy as np
import networkx as nx


def _pagerank_power_numpy(
    G: nx.DiGraph, alpha: float = 0.85, weight: str = "freq", max_iter: int = 100, tol: float = 1.0e-6
) -> dict[str, float]:
    """Power-iteration PageRank using numpy only (no scipy dependency)."""
    n = G.number_of_nodes()
    if n == 0:
        return {}

    nodes = list(G.nodes())
    idx = {node: i for i, node in enumerate(nodes)}

    out_weight = np.zeros(n, dtype=float)
    for u, _, data in G.edges(data=True):
        out_weight[idx[u]] += float(data.get(weight, 1.0))

    dangling = np.where(out_weight == 0.0)[0]
    pr = np.full(n, 1.0 / n, dtype=float)

    for _ in range(max_iter):
        prev_pr = pr.copy()
        pr[:] = (1.0 - alpha) / n

        # Handle incoming edges
        for v, u, data in G.edges(data=True):
            w = float(data.get(weight, 1.0))
            denom = out_weight[idx[v]]
            if denom > 0:
                pr[idx[u]] += alpha * prev_pr[idx[v]] * (w / denom)

        # Distribute dangling nodes
        if len(dangling) > 0:
            pr += alpha * prev_pr[dangling].sum() / n

        # Check convergence (L1 norm)
        if np.abs(pr - prev_pr).sum() < tol:
            break

    return {node: float(score) for node, score in zip(nodes, pr)}


def compute_pagerank_and_risk(G: nx.DiGraph, alpha: float = 0.85) -> tuple[dict[str, float], dict[str, float]]:
    """Compute PageRank (freq-weighted) and normalize to risk [0,1]."""
    if G.number_of_nodes() == 0:
        return {}, {}

    pr = _pagerank_power_numpy(G, alpha=alpha, weight="freq")
    if not pr:
        return {}, {}

    min_pr = min(pr.values())
    max_pr = max(pr.values())
    denom = (max_pr - min_pr) + 1e-12
    risk = {node: (score - min_pr) / denom for node, score in pr.items()}
    return pr, risk
