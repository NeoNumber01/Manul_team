from __future__ import annotations

import networkx as nx
import numpy as np


class TrafficSystem:
    """Lightweight PageRank-based weighting for major German hubs."""

    def __init__(self) -> None:
        # Define directed connections to approximate hub importance
        self.connections = [
            ("Frankfurt Hbf", "Mannheim Hbf"),
            ("Frankfurt Hbf", "Köln Hbf"),
            ("Frankfurt Hbf", "Würzburg Hbf"),
            ("Frankfurt Hbf", "Berlin Hbf"),
            ("Mannheim Hbf", "Stuttgart Hbf"),
            ("Stuttgart Hbf", "Munich Hbf"),
            ("Stuttgart Hbf", "Heilbronn Hbf"),
            ("Munich Hbf", "Nürnberg Hbf"),
            ("Nürnberg Hbf", "Leipzig Hbf"),
            ("Leipzig Hbf", "Berlin Hbf"),
            ("Berlin Hbf", "Hamburg Hbf"),
            ("Hamburg Hbf", "Köln Hbf"),
            ("Karlsruhe Hbf", "Mannheim Hbf"),
            ("Karlsruhe Hbf", "Stuttgart Hbf"),
            ("Hannover Hbf", "Berlin Hbf"),
            ("Hannover Hbf", "Frankfurt Hbf"),
        ]

        self.G = nx.DiGraph()
        self.G.add_edges_from(self.connections)

        self.pagerank_scores = self._compute_pagerank()

    def _compute_pagerank(self) -> dict:
        """Compute PageRank (alpha=0.85) using a NumPy-only power iteration (SciPy not required)."""
        return self._pagerank_numpy(self.G, alpha=0.85, max_iter=100, tol=1e-6)

    @staticmethod
    def _pagerank_numpy(G: nx.DiGraph, alpha: float = 0.85, max_iter: int = 100, tol: float = 1e-6) -> dict:
        """Power-iteration PageRank using numpy only."""
        n = G.number_of_nodes()
        if n == 0:
            return {}

        nodes = list(G.nodes())
        idx = {node: i for i, node in enumerate(nodes)}

        out_weight = np.zeros(n, dtype=float)
        for u, _, data in G.edges(data=True):
            out_weight[idx[u]] += float(data.get("weight", 1.0))

        dangling = np.where(out_weight == 0.0)[0]
        pr = np.full(n, 1.0 / n, dtype=float)

        for _ in range(max_iter):
            prev_pr = pr.copy()
            pr[:] = (1.0 - alpha) / n

            for v, u, data in G.edges(data=True):
                w = float(data.get("weight", 1.0))
                denom = out_weight[idx[v]]
                if denom > 0:
                    pr[idx[u]] += alpha * prev_pr[idx[v]] * (w / denom)

            if len(dangling) > 0:
                pr += alpha * prev_pr[dangling].sum() / n

            if np.abs(pr - prev_pr).sum() < tol:
                break

        return {node: float(score) for node, score in zip(nodes, pr)}

    def get_rank(self, station_name: str) -> float:
        """Fetch weight with light fuzzy matching."""
        if station_name in self.pagerank_scores:
            return self.pagerank_scores[station_name]

        for name, score in self.pagerank_scores.items():
            if name in station_name or station_name in name:
                return score
        return 0.015
