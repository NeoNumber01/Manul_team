"""Routing utilities for fastest vs robust paths."""

import networkx as nx


def shortest_path_fastest(G: nx.DiGraph, src: str, dst: str) -> list[str]:
    """Shortest path minimizing travel time."""
    return nx.shortest_path(G, source=src, target=dst, weight="time_sec")


def shortest_path_robust(G: nx.DiGraph, src: str, dst: str, risk: dict[str, float], lam: float) -> list[str]:
    """Shortest path balancing time and node risk."""

    def weight(u: str, v: str, data: dict) -> float:
        base = float(data.get("time_sec", 60.0))
        return base + lam * float(risk.get(v, 0.0))

    return nx.shortest_path(G, source=src, target=dst, weight=weight)


def path_total_time(G: nx.DiGraph, path: list[str]) -> float:
    """Total travel time along a path in seconds."""
    if len(path) < 2:
        return 0.0
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = G.get_edge_data(u, v, default={})
        total += float(data.get("time_sec", 60.0))
    return total


def path_risk_sum(risk: dict[str, float], path: list[str]) -> float:
    """Sum risk across nodes (excluding the source)."""
    if len(path) <= 1:
        return 0.0
    return sum(float(risk.get(node, 0.0)) for node in path[1:])


def count_top_hubs_on_path(path: list[str], top_hubs: set[str]) -> int:
    """Count how many nodes in the path are within the top hub set."""
    return sum(1 for node in path if node in top_hubs)
