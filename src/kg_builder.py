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

