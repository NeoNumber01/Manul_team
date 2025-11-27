"""Build RDFLib graphs from GTFS-derived data."""

import pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF


def build_kg_from_stops(stops_df: "pd.DataFrame", ont_ns: Namespace) -> Graph:
    """Create a knowledge graph from stop records."""
    graph = Graph()
    graph.bind("ont", ont_ns)

    for row in stops_df.itertuples(index=False):
        stop_uri = URIRef(ont_ns[f"stop/{row.stop_id}"])
        graph.add((stop_uri, RDF.type, ont_ns.Stop))
        graph.add((stop_uri, ont_ns.stopId, Literal(row.stop_id)))
        graph.add((stop_uri, ont_ns.stopName, Literal(row.stop_name)))
        graph.add((stop_uri, ont_ns.lat, Literal(float(row.stop_lat))))
        graph.add((stop_uri, ont_ns.lon, Literal(float(row.stop_lon))))

    return graph


def add_edges_to_kg(
    kg: Graph,
    edges_df: pd.DataFrame,
    ont_ns: Namespace,
    *,
    lightweight: bool = True,
) -> Graph:
    """
    Augment KG with edges.

    lightweight=True: only add ont:nextStop triples (adjacency only).
    lightweight=False: also create ont:Connection nodes with metadata (heavier, for small demos).
    """
    kg.bind("ont", ont_ns)

    for row in edges_df.itertuples(index=False):
        from_id = str(row.from_stop_id)
        to_id = str(row.to_stop_id)
        from_uri = URIRef(ont_ns[f"stop/{from_id}"])
        to_uri = URIRef(ont_ns[f"stop/{to_id}"])

        kg.add((from_uri, ont_ns.nextStop, to_uri))

        if lightweight:
            continue

        conn_uri = URIRef(ont_ns[f"conn/{from_id}__{to_id}"])
        kg.add((conn_uri, RDF.type, ont_ns.Connection))
        kg.add((conn_uri, ont_ns.fromStop, from_uri))
        kg.add((conn_uri, ont_ns.toStop, to_uri))
        kg.add((conn_uri, ont_ns.tripCount, Literal(int(row.trip_count))))

        avg_time = getattr(row, "avg_travel_time_sec", None)
        if avg_time is not None and not pd.isna(avg_time):
            kg.add((conn_uri, ont_ns.avgTravelTimeSec, Literal(float(avg_time))))

    return kg
