"""On-disk caching helpers for graphs and pagerank."""

import pickle
from pathlib import Path
from typing import Dict, Tuple

import networkx as nx

from src.kg_to_graph import NodeInfo


def save_graph_cache(path: Path, G: nx.DiGraph, node_info: Dict[str, NodeInfo]) -> None:
    """Persist graph and node info."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({"G": G, "node_info": node_info}, f)


def load_graph_cache(path: Path):
    """Load graph and node info if cache exists."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = pickle.load(f)
    return data.get("G"), data.get("node_info")


def save_pagerank_cache(path: Path, pagerank: dict[str, float], risk: dict[str, float]) -> None:
    """Persist pagerank and risk dictionaries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({"pagerank": pagerank, "risk": risk}, f)


def load_pagerank_cache(path: Path):
    """Load pagerank and risk from cache if available."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = pickle.load(f)
    return data.get("pagerank"), data.get("risk")
