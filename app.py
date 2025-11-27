from pathlib import Path
import hashlib

import streamlit as st
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

from src.gtfs_loader import load_stops_from_gtfs_zip
from src.kg_builder import build_kg_from_stops

st.set_page_config(page_title="Transit Knowledge Graph Demo", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
KG_CACHE_PATH = DATA_DIR / "kg_demo.ttl"

ONT = Namespace("http://example.org/ont/")

DEFAULT_SPARQL = """
PREFIX ont: <http://example.org/ont/>
SELECT ?s ?name ?next
WHERE {
  ?s a ont:Stop .
  OPTIONAL { ?s ont:stopName ?name . }
  OPTIONAL { ?s ont:nextStop ?next . }
}
"""


GTFS_SPARQL = """
PREFIX ont: <http://example.org/ont/>
SELECT ?s ?id ?name ?lat ?lon
WHERE {
  ?s a ont:Stop .
  OPTIONAL { ?s ont:stopId ?id . }
  OPTIONAL { ?s ont:stopName ?name . }
  OPTIONAL { ?s ont:lat ?lat . }
  OPTIONAL { ?s ont:lon ?lon . }
}
LIMIT 200
"""


def load_or_create_kg(path: Path) -> tuple[Graph, bool]:
    """Load a KG from TTL if present, else create the toy KG and persist it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = Graph()
    if path.exists():
        graph.parse(path, format="turtle")
        return graph, True

    graph.bind("ont", ONT)
    stop_a = URIRef(ONT["Stop_A"])
    stop_b = URIRef(ONT["Stop_B"])

    graph.add((stop_a, RDF.type, ONT.Stop))
    graph.add((stop_b, RDF.type, ONT.Stop))
    graph.add((stop_a, ONT.stopName, Literal("Hauptbahnhof")))
    graph.add((stop_b, ONT.stopName, Literal("Universität")))
    graph.add((stop_a, ONT.nextStop, stop_b))

    graph.serialize(destination=path, format="turtle")
    return graph, False


def load_gtfs_kg(gtfs_zip_bytes: bytes) -> tuple[Graph, bool, Path]:
    """Load GTFS-derived KG from cache if available, else build and persist it."""
    digest = hashlib.sha256(gtfs_zip_bytes).hexdigest()
    cache_path = DATA_DIR / f"kg_gtfs_{digest[:12]}.ttl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    if cache_path.exists():
        graph.parse(cache_path, format="turtle")
        return graph, True, cache_path

    stops_df = load_stops_from_gtfs_zip(gtfs_zip_bytes)
    graph = build_kg_from_stops(stops_df, ONT)
    graph.serialize(destination=cache_path, format="turtle")
    return graph, False, cache_path


def main() -> None:
    st.title("Transit Knowledge Graph — Minimal Demo (RDFLib + SPARQL)")

    st.sidebar.subheader("Static Data (GTFS)")
    uploaded_gtfs = st.sidebar.file_uploader("Upload GTFS zip", type=["zip"])
    use_demo_kg = st.sidebar.checkbox("Use demo KG", value=True)

    kg: Graph | None = None
    kg_label = "Demo KG"
    default_query = DEFAULT_SPARQL
    status_msg = ""

    prefer_gtfs = uploaded_gtfs is not None and not use_demo_kg
    if prefer_gtfs and uploaded_gtfs is not None:
        try:
            gtfs_bytes = uploaded_gtfs.getvalue()
            kg, loaded_from_cache, cache_path = load_gtfs_kg(gtfs_bytes)
            kg_label = "GTFS KG"
            default_query = GTFS_SPARQL
            status_msg = (
                f"Loaded GTFS KG from cache: {cache_path}"
                if loaded_from_cache
                else f"Built GTFS KG and cached to: {cache_path}"
            )
        except Exception as exc:
            st.error(f"Failed to load GTFS KG: {exc}")
            st.info("Falling back to demo KG.")

    if kg is None:
        kg, loaded_from_cache = load_or_create_kg(KG_CACHE_PATH)
        status_msg = (
            f"Loaded demo KG from cache: {KG_CACHE_PATH}"
            if loaded_from_cache
            else f"Created demo KG and saved to cache: {KG_CACHE_PATH}"
        )

    st.success(status_msg)
    st.write(f"Using: **{kg_label}** | Triples: **{len(kg)}**")

    st.subheader("Local SPARQL Query")
    sparql_query = st.text_area("SPARQL query", value=default_query, height=200)

    try:
        results = kg.query(sparql_query)
        rows = []
        for r in results:
            row_data = {str(k): v for k, v in r.asdict().items()}
            rows.append(
                {
                    str(var): str(row_data.get(str(var))) if row_data.get(str(var)) is not None else ""
                    for var in results.vars
                }
            )

        max_rows = 200
        display_rows = rows[:max_rows]
        if len(rows) > max_rows:
            st.info(f"Showing first {max_rows} of {len(rows)} rows.")

        st.dataframe(display_rows, use_container_width=True)
    except Exception as exc:
        st.error(f"Query failed: {exc}")


if __name__ == "__main__":
    main()
