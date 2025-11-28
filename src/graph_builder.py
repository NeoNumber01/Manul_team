import networkx as nx
import pandas as pd


def build_graph(stops_df: pd.DataFrame, stop_times_df: pd.DataFrame) -> nx.DiGraph:
    """
    Build a directed graph from GTFS stops.txt and stop_times.txt.

    - Each stop_id becomes a node.
    - Edges are created for each consecutive pair of stops in the same trip.
    """

    G = nx.DiGraph()

    # ----------------------------------------------------------
    # 1. Add all stops as graph nodes
    # ----------------------------------------------------------
    for _, row in stops_df.iterrows():
        G.add_node(
            row["stop_id"],
            stop_name=row["stop_name"],
            lat=row["stop_lat"],
            lon=row["stop_lon"]
        )

    # ----------------------------------------------------------
    # 2. Sort stop_times to ensure correct sequence order
    # ----------------------------------------------------------
    stop_times_df = stop_times_df.sort_values(
        ["trip_id", "stop_sequence"]
    )

    # ----------------------------------------------------------
    # 3. Build edges between consecutive stops in each trip
    # ----------------------------------------------------------
    prev_stop = None
    prev_trip = None

    for _, row in stop_times_df.iterrows():
        trip_id = row["trip_id"]
        stop_id = row["stop_id"]

        # if same trip → add edge prev → current
        if prev_trip == trip_id:
            G.add_edge(prev_stop, stop_id, weight=1)

        # update state
        prev_stop = stop_id
        prev_trip = trip_id

    return G
