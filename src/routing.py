import networkx as nx
import pandas as pd


def shortest_path_fastest(G: nx.DiGraph, source: str, target: str):
    """
    Compute the fastest path between two stops based on edge weights.
    Edge weight is assumed to be 'weight' (default = 1).

    Returns:
        path (list of stop_ids) or None if no path exists
    """
    try:
        path = nx.shortest_path(G, source=source, target=target, weight="weight")
        return path
    except nx.NetworkXNoPath:
        return None
    except nx.NodeNotFound:
        return None


def path_total_time(G: nx.DiGraph, path: list) -> float:
    """
    Sum all edge weights along the path.
    If edges have time-based weights, this returns total travel time.
    """
    if path is None:
        return float("inf")

    total = 0.0
    for i in range(len(path) - 1):
        u = path[i]
        v = path[i + 1]
        weight = G[u][v].get("weight", 1)
        total += weight

    return total


def count_top_hubs_on_path(ranking_df: pd.DataFrame, path: list, top_n: int = 20) -> int:
    """
    Count how many high-PageRank stations lie on the path.

    ranking_df must contain:
        index = stop_id
        pagerank column

    This can be used to detect whether path goes through main hubs.
    """
    if path is None:
        return 0

    # select top N hubs by PageRank
    top_hubs = set(ranking_df.sort_values("pagerank", ascending=False).head(top_n).index)

    count = sum(1 for stop in path if stop in top_hubs)
    return count
