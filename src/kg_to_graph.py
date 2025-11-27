"""Convert data to NetworkX graphs and related helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import networkx as nx
import pandas as pd
from rdflib import Graph, Namespace
from rdflib.namespace import RDF


@dataclass(frozen=True)
class NodeInfo:
    station_key: str
    display_name: str


def extract_stop_id_from_uri(uri: str) -> str:
    """Extract stop_id from ont:stop/<id> URI."""
    if "/stop/" in uri:
        return uri.rsplit("/stop/", 1)[-1]
    return uri.rsplit("/", 1)[-1]


def build_networkx_from_edges_and_stations(
    edges_df: pd.DataFrame,
    stops_df: pd.DataFrame,
) -> Tuple[nx.DiGraph, Dict[str, NodeInfo]]:
    """
    Build graph where nodes are stations (merged by parent_station or stop_name),
    using only edges that exist.
    """
    def _norm_stop_id(val) -> str:
        s = str(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s

    station_key_by_stop: Dict[str, str] = {}
    name_by_station: Dict[str, str] = {}

    stops_df = stops_df.copy()
    stops_df["stop_id"] = stops_df["stop_id"].map(_norm_stop_id)
    stops_df["parent_station"] = stops_df["parent_station"].fillna("").astype(str)

    for row in stops_df.itertuples(index=False):
        sid = _norm_stop_id(row.stop_id)
        parent = getattr(row, "parent_station", None)
        stop_name = getattr(row, "stop_name", "") or ""
        if parent and str(parent).strip():
            key = f"station:{parent}"
        else:
            key = f"name:{stop_name}"
        station_key_by_stop[sid] = key
        # First name encountered wins; good enough for display
        if key not in name_by_station and stop_name:
            name_by_station[key] = stop_name

    if edges_df.empty:
        return nx.DiGraph(), {}

    station_edges = edges_df.copy()
    station_edges["from_stop_id"] = station_edges["from_stop_id"].map(_norm_stop_id)
    station_edges["to_stop_id"] = station_edges["to_stop_id"].map(_norm_stop_id)
    station_edges["from_station"] = station_edges["from_stop_id"].map(station_key_by_stop)
    station_edges["to_station"] = station_edges["to_stop_id"].map(station_key_by_stop)

    grouped = station_edges.groupby(["from_station", "to_station"], as_index=False).agg(
        trip_count=("trip_count", "sum"),
        avg_travel_time_sec=("avg_travel_time_sec", "mean"),
    )

    G = nx.DiGraph()
    for row in grouped.itertuples(index=False):
        u = row.from_station
        v = row.to_station
        freq = int(row.trip_count) if getattr(row, "trip_count", None) is not None else 1
        time_sec = row.avg_travel_time_sec
        time_sec = float(time_sec) if pd.notna(time_sec) else 60.0
        if G.has_edge(u, v):
            # Update freq and simple average time
            G[u][v]["freq"] += freq
            G[u][v]["time_sec"] = (G[u][v]["time_sec"] + time_sec) / 2.0
        else:
            G.add_edge(u, v, freq=freq, time_sec=time_sec)

    node_info: Dict[str, NodeInfo] = {}
    for station_key in G.nodes:
        display_name = name_by_station.get(station_key, station_key)
        node_info[station_key] = NodeInfo(station_key=station_key, display_name=display_name)
        G.nodes[station_key]["name"] = display_name

    return G, node_info


def top_k_pagerank(G: nx.DiGraph, k: int, weight: str = "freq") -> Dict[str, float]:
    """Return top-k PageRank scores."""
    pr = nx.pagerank(G, weight=weight) if G.number_of_nodes() > 0 else {}
    return dict(sorted(pr.items(), key=lambda item: item[1], reverse=True)[:k])
