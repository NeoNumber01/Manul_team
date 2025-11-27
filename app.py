from pathlib import Path
import hashlib

import pandas as pd
import streamlit as st
import pydeck as pdk
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

from src.edge_builder import build_edge_stats, load_edges_cache, save_edges_cache
from src.graph_cache import (
    load_graph_cache,
    load_pagerank_cache,
    save_graph_cache,
    save_pagerank_cache,
)
from src.gtfs_loader import load_stops_from_gtfs_zip, load_stop_times_from_gtfs_zip
from src.kg_builder import add_edges_to_kg, build_kg_from_stops
from src.kg_to_graph import build_networkx_from_edges_and_stations
from src.ranking import compute_pagerank_and_risk
from src.routing import (
    count_top_hubs_on_path,
    path_risk_sum,
    path_total_time,
    shortest_path_fastest,
    shortest_path_robust,
)
from src.viz import (
    build_legs_df,
    build_stop_lookup,
    compute_view_state,
    filter_points_to_germany,
    path_to_line_df,
    path_to_points_df,
)
from src.ui import station_picker

st.set_page_config(page_title="Transit Knowledge Graph Demo", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
KG_CACHE_PATH = DATA_DIR / "kg_demo.ttl"
BUNDLED_GTFS_PATH = DATA_DIR / "gtfs" / "default_gtfs.zip"
DEFAULT_GTFS_PATH = BUNDLED_GTFS_PATH

ONT = Namespace("http://example.org/ont/")
ENABLE_PAGERANK = False

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

EDGES_SPARQL = """
PREFIX ont: <http://example.org/ont/>
SELECT ?from ?to ?count ?time
WHERE {
  ?c a ont:Connection ;
     ont:fromStop ?from ;
     ont:toStop ?to ;
     ont:tripCount ?count .
  OPTIONAL { ?c ont:avgTravelTimeSec ?time . }
}
ORDER BY DESC(?count)
LIMIT 50
"""

NEIGHBORS_TEMPLATE = """
PREFIX ont: <http://example.org/ont/>
SELECT ?next ?name
WHERE {
  ?s a ont:Stop ;
     ont:stopId ?id .
  FILTER(STR(?id) = "%STOP_ID%")
  ?s ont:nextStop ?next .
  OPTIONAL { ?next ont:stopName ?name . }
}
LIMIT 100
"""


def stops_df_from_kg(kg: Graph) -> pd.DataFrame:
    """Extract stops from KG into a DataFrame; best-effort for demo KG."""
    query = """
    PREFIX ont: <http://example.org/ont/>
    SELECT ?s ?name ?lat ?lon
    WHERE {
      ?s a ont:Stop .
      OPTIONAL { ?s ont:stopName ?name . }
      OPTIONAL { ?s ont:lat ?lat . }
      OPTIONAL { ?s ont:lon ?lon . }
    }
    """
    rows = []
    for r in kg.query(query):
        rows.append(
            {
                "stop_id": str(r.s).rsplit("/stop/", 1)[-1],
                "stop_name": str(r.name) if getattr(r, "name", None) else "",
                "stop_lat": float(r.lat) if getattr(r, "lat", None) else 0.0,
                "stop_lon": float(r.lon) if getattr(r, "lon", None) else 0.0,
                "parent_station": None,
            }
        )
    return pd.DataFrame(rows)


def edges_df_from_kg_nextstop(kg: Graph) -> pd.DataFrame:
    """Extract nextStop edges as a fallback for demo KG."""
    query = """
    PREFIX ont: <http://example.org/ont/>
    SELECT ?from ?to
    WHERE {
      ?from ont:nextStop ?to .
    }
    """
    rows = []
    for r in kg.query(query):
        rows.append(
            {
                "from_stop_id": str(r["from"]).rsplit("/stop/", 1)[-1],
                "to_stop_id": str(r["to"]).rsplit("/stop/", 1)[-1],
                "trip_count": 1,
                "avg_travel_time_sec": 60.0,
            }
        )
    return pd.DataFrame(rows)


def build_node_to_stop_id(node_info: dict[str, any], stops_df: pd.DataFrame) -> dict[str, str]:
    """Map graph node keys to representative stop_ids for coordinates."""
    # Recreate station key logic to map station keys back to a stop_id.
    def _norm_stop_id(val) -> str:
        s = str(val)
        return s[:-2] if s.endswith(".0") else s

    station_key_by_stop: dict[str, str] = {}
    for row in stops_df.itertuples(index=False):
        sid = _norm_stop_id(row.stop_id)
        parent = getattr(row, "parent_station", None)
        stop_name = getattr(row, "stop_name", "") or ""
        if parent and str(parent).strip():
            key = f"station:{parent}"
        else:
            key = f"name:{stop_name}"
        station_key_by_stop[sid] = key

    # Reverse map: station key -> first stop_id encountered
    stop_id_by_station: dict[str, str] = {}
    for sid, skey in station_key_by_stop.items():
        if skey not in stop_id_by_station:
            stop_id_by_station[skey] = sid

    node_to_stop: dict[str, str] = {}
    for node_key in node_info.keys():
        if node_key in stop_id_by_station:
            node_to_stop[node_key] = stop_id_by_station[node_key]
        else:
            # fallback: best-effort parse last segment
            node_to_stop[node_key] = node_key.rsplit(":", 1)[-1].rsplit("/", 1)[-1]

    return node_to_stop


def load_default_gtfs_bytes() -> bytes:
    """Load bundled GTFS bytes or stop with a clear error."""
    if not DEFAULT_GTFS_PATH.exists():
        st.error(f"Default GTFS zip not found at {DEFAULT_GTFS_PATH}. Please place a GTFS feed there.")
        st.stop()
    return DEFAULT_GTFS_PATH.read_bytes()


def load_gtfs_kg(
    gtfs_zip_bytes: bytes,
    *,
    build_edges: bool,
    max_trips: int | None = None,
    lightweight_edges: bool = True,
) -> tuple[
    Graph,
    bool,
    Path,
    pd.DataFrame | None,
    Path | None,
    bool,
    str | None,
    bool,
    pd.DataFrame,
    str,
]:
    """
    Load GTFS-derived KG with optional edges from cache if available, else build and persist it.

    Returns: (kg, loaded_from_cache, kg_cache_path, edges_df, edges_cache_path, edges_built, edge_warning, edges_from_cache, stops_df, digest)
    """
    digest = hashlib.sha256(gtfs_zip_bytes).hexdigest()
    base_name = f"kg_gtfs_{digest[:12]}"
    cache_dir = DATA_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if build_edges:
        trip_suffix = f"_trips{max_trips}" if max_trips else "_alltrips"
        kg_cache_path = DATA_DIR / f"{base_name}_v3_light{trip_suffix}.ttl"
        edges_cache_path = cache_dir / f"edges_{digest[:12]}{trip_suffix}.parquet"
    else:
        kg_cache_path = DATA_DIR / f"{base_name}_v3_stops.ttl"
        edges_cache_path = None

    edges_df: pd.DataFrame | None = None
    edges_from_cache = False
    edges_built = False
    edge_warning: str | None = None

    stops_df = load_stops_from_gtfs_zip(gtfs_zip_bytes)

    # Try to load edges cache first if needed
    if build_edges and edges_cache_path is not None:
        edges_df = load_edges_cache(edges_cache_path)
        if edges_df is not None and len(edges_df) > 0:
            edges_from_cache = True
        else:
            edges_df = None

    # Load KG cache if present
    if kg_cache_path.exists():
        graph = Graph()
        graph.parse(kg_cache_path, format="turtle")
        if build_edges and edges_cache_path is not None and (edges_df is None or len(edges_df) == 0):
            try:
                stop_times_df = load_stop_times_from_gtfs_zip(gtfs_zip_bytes)
                edges_df = build_edge_stats(stop_times_df, max_trips=max_trips)
                save_edges_cache(edges_df, edges_cache_path)
                edges_built = True
            except ValueError as exc:
                edge_warning = f"Edges skipped: {exc}"
            except Exception as exc:  # noqa: BLE001
                edge_warning = f"Edges skipped due to error: {exc}"
        return (
            graph,
            True,
            kg_cache_path,
            edges_df,
            edges_cache_path,
            edges_built,
            edge_warning,
            edges_from_cache,
            stops_df,
            digest,
        )

    graph = build_kg_from_stops(stops_df, ONT)

    if build_edges:
        try:
            if edges_df is None or len(edges_df) == 0:
                stop_times_df = load_stop_times_from_gtfs_zip(gtfs_zip_bytes)
                edges_df = build_edge_stats(stop_times_df, max_trips=max_trips)
                save_edges_cache(edges_df, edges_cache_path)
                edges_built = True
            graph = add_edges_to_kg(graph, edges_df, ONT, lightweight=lightweight_edges)
        except ValueError as exc:
            edge_warning = f"Edges skipped: {exc}"
        except Exception as exc:  # noqa: BLE001
            edge_warning = f"Edges skipped due to error: {exc}"

    graph.serialize(destination=kg_cache_path, format="turtle")
    return (
        graph,
        False,
        kg_cache_path,
        edges_df,
        edges_cache_path,
        edges_built,
        edge_warning,
        edges_from_cache,
        stops_df,
        digest,
    )


def main() -> None:
    st.title("Transit Knowledge Graph — Minimal Demo (RDFLib + SPARQL)")

    st.sidebar.subheader("Data source")
    st.sidebar.info(f"Bundled GTFS: {DEFAULT_GTFS_PATH}")

    kg: Graph | None = None
    default_query = GTFS_SPARQL
    status_msg = ""
    edge_warning: str | None = None
    kg_cache_path: Path | None = None
    edges_df: pd.DataFrame | None = None
    edges_cache_path: Path | None = None
    edges_from_cache = False
    stops_df: pd.DataFrame | None = None
    digest: str = ""

    gtfs_bytes = load_default_gtfs_bytes()

    try:
        with st.spinner("Loading GTFS KG..."):
            (
                kg,
                loaded_from_cache,
                cache_path,
                edges_df,
                edges_cache_path,
                edges_built,
                edge_warning,
                edges_from_cache,
                stops_df,
                digest,
            ) = load_gtfs_kg(
                gtfs_bytes,
                build_edges=True,
                max_trips=None,
                lightweight_edges=True,
            )
        kg_cache_path = cache_path
        status_msg = (
            f"Loaded GTFS KG from cache: {cache_path}"
            if loaded_from_cache
            else f"Built GTFS KG and saved to cache: {cache_path}"
        )
        if edges_cache_path:
            if edges_from_cache:
                status_msg += f" (edges from cache: {edges_cache_path})"
            elif edges_built:
                status_msg += " (edges built and cached)"
    except Exception as exc:
        st.error(f"Failed to load GTFS KG: {exc}")
        st.stop()

    st.success(status_msg)
    st.write(f"Using: **GTFS KG (bundled)** | GTFS path: {DEFAULT_GTFS_PATH} | Triples: **{len(kg)}**")
    if edge_warning:
        st.warning(edge_warning)
    if edges_cache_path:
        cache_state = (
            "from cache"
            if edges_from_cache
            else ("built this run" if edges_df is not None else "missing (using KG edges)")
        )
        st.write(f"Edges cache: {edges_cache_path} ({cache_state})")

    # Cache paths for graph and pagerank
    cache_dir = DATA_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    graph_cache_path = cache_dir / f"graph_{digest[:12]}.pkl"
    pr_cache_path = cache_dir / f"pr_{digest[:12]}.pkl"

    # Build or load graph
    graph_loaded_from_cache = False
    pr_loaded_from_cache = False
    if edges_df is None:
        edges_df = edges_df_from_kg_nextstop(kg)
    if stops_df is None:
        stops_df = stops_df_from_kg(kg)

    G = None
    node_info = {}

    cached_graph = load_graph_cache(graph_cache_path)
    if cached_graph is not None and cached_graph[0] is not None:
        G, node_info = cached_graph
        if G.number_of_nodes() >= 2 and G.number_of_edges() >= 1:
            graph_loaded_from_cache = True
        else:
            # Cached graph is empty/invalid; rebuild
            G, node_info = build_networkx_from_edges_and_stations(edges_df, stops_df)
            save_graph_cache(graph_cache_path, G, node_info)
            graph_loaded_from_cache = False
    else:
        G, node_info = build_networkx_from_edges_and_stations(edges_df, stops_df)
        save_graph_cache(graph_cache_path, G, node_info)

    # Pagerank / risk
    pr = {}
    risk = {}
    if ENABLE_PAGERANK:
        cached_pr = load_pagerank_cache(pr_cache_path)
        if cached_pr is not None and cached_pr[0] is not None:
            pr, risk = cached_pr
            if pr:
                pr_loaded_from_cache = True
            else:
                pr, risk = compute_pagerank_and_risk(G)
                save_pagerank_cache(pr_cache_path, pr, risk)
                pr_loaded_from_cache = False
        else:
            pr, risk = compute_pagerank_and_risk(G)
            save_pagerank_cache(pr_cache_path, pr, risk)

    st.subheader("Routing")
    st.caption(
        f"Routing mode: {'Fastest only (PageRank disabled)' if not ENABLE_PAGERANK else 'Fastest vs Robust'} | "
        f"Graph nodes: {G.number_of_nodes()} | edges: {G.number_of_edges()} | "
        f"Graph cache: {'cache' if graph_loaded_from_cache else 'rebuilt'}"
        + ("" if not ENABLE_PAGERANK else f" | PageRank: {'cache' if pr_loaded_from_cache else 'computed'}")
    )

    routing_enabled = st.checkbox("Enable routing demo", value=True)
    if routing_enabled and (G.number_of_nodes() < 2 or G.number_of_edges() == 0):
        st.warning("Routing graph has insufficient data (need at least 2 nodes and 1 edge).")

    if routing_enabled and G.number_of_nodes() >= 2 and G.number_of_edges() > 0:
        def _label(station_key: str) -> str:
            info = node_info.get(station_key)
            if info and info.display_name:
                return f"{info.display_name} ({station_key})"
            return station_key

        all_options = sorted(node_info.keys(), key=lambda sid: (node_info[sid].display_name or sid))
        if len(all_options) < 2:
            st.warning("Not enough stops to compute routes.")
        else:
            options_list = [(key, node_info[key].display_name or key) for key in all_options]

            with st.form("route_form"):
                src_id = station_picker(
                    title="Start station",
                    options=options_list,
                    key_prefix="start",
                    default_node=all_options[0],
                )
                dst_id = station_picker(
                    title="End station",
                    options=options_list,
                    key_prefix="end",
                    default_node=all_options[1] if len(all_options) > 1 else all_options[0],
                )

                submitted = st.form_submit_button("Compute route")

            if ENABLE_PAGERANK:
                lam = st.slider("Lambda (risk weight)", min_value=0.0, max_value=300.0, value=50.0, step=5.0)
            else:
                st.caption("Robust routing disabled (PageRank off).")

            if submitted:
                try:
                    with st.spinner("Computing routes..."):
                        fastest_path = shortest_path_fastest(G, src_id, dst_id)
                        fastest_time_sec = path_total_time(G, fastest_path)
                        top10 = {}
                        robust_path = []
                        robust_time_sec = 0.0
                        fastest_hubs = 0
                        robust_hubs = 0
                        fastest_risk = 0.0
                        robust_risk = 0.0

                        if ENABLE_PAGERANK:
                            robust_path = shortest_path_robust(G, src_id, dst_id, risk, lam)
                            robust_time_sec = path_total_time(G, robust_path)
                            top10 = dict(sorted(pr.items(), key=lambda item: item[1], reverse=True)[:10])
                            top10_ids = set(top10.keys())
                            fastest_hubs = count_top_hubs_on_path(fastest_path, top10_ids)
                            robust_hubs = count_top_hubs_on_path(robust_path, top10_ids)
                            fastest_risk = path_risk_sum(risk, fastest_path)
                            robust_risk = path_risk_sum(risk, robust_path)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Routing failed: {exc}")
                else:
                    def _fmt_minutes(sec: float) -> str:
                        return f"{sec/60:.1f} min"

                    def _fmt_path(path: list[str]) -> str:
                        return " \u2192 ".join(_label(sid) for sid in path) if path else "No path"

                    st.markdown("**Fastest route**")
                    st.write(f"Total time: {_fmt_minutes(fastest_time_sec)}")
                    st.write(f"Stops: {len(fastest_path)}")
                    st.write(_fmt_path(fastest_path))

                    # Build map and legs
                    stop_lookup = build_stop_lookup(stops_df)
                    node_to_stop_id = build_node_to_stop_id(node_info, stops_df)
                    points_df = path_to_points_df(fastest_path, node_to_stop_id, stop_lookup)
                    line_df = path_to_line_df(points_df)
                    legs_df = build_legs_df(G, fastest_path, node_info)

                    st.session_state["last_path_nodes"] = fastest_path
                    st.session_state["last_points_df"] = points_df
                    st.session_state["last_legs_df"] = legs_df

                    if len(points_df) >= 2:
                        points_df = points_df.copy()
                        points_df["color"] = [[220, 0, 0, 220] for _ in range(len(points_df))]
                        points_df["radius"] = 120
                        points_df_de = filter_points_to_germany(points_df)
                        if len(points_df_de) < len(points_df):
                            st.caption("Some points were outside Germany and were ignored for framing.")
                        points_df = points_df_de if len(points_df_de) >= 2 else points_df
                        line_df = path_to_line_df(points_df)  # Rebuild line to match filtered points
                        line_df["color"] = [[30, 120, 200, 220]]  # blue line
                        view_state = compute_view_state(points_df)
                        layers = [
                            pdk.Layer(
                                "PathLayer",
                                data=line_df,
                                get_path="path",
                                get_width=6,
                                width_min_pixels=6,
                                rounded=True,
                                opacity=0.85,
                                get_color="color",
                            ),
                            pdk.Layer(
                                "ScatterplotLayer",
                                data=points_df,
                                get_position=["lon", "lat"],
                                get_radius="radius",
                                get_fill_color="color",
                                pickable=True,
                            ),
                        ]
                        tooltip = {"text": "{idx}. {name}"}
                        st.markdown("**Route map**")
                        st.pydeck_chart(
                            pdk.Deck(
                                layers=layers,
                                initial_view_state=view_state,
                                tooltip=tooltip,
                                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                            ),
                            use_container_width=True,
                        )
                    else:
                        st.warning("Not enough coordinates to draw the route on the map.")

                    if not legs_df.empty:
                        st.markdown("**Leg-by-leg details**")
                        st.dataframe(legs_df, use_container_width=True)
                    else:
                        st.info("No leg details available.")

                    if ENABLE_PAGERANK and robust_path:
                        col_fast, col_rob = st.columns(2)
                        with col_fast:
                            st.markdown("**Fastest (with risk stats)**")
                            st.write(f"Total time: {_fmt_minutes(fastest_time_sec)}")
                            st.write(f"Stops: {len(fastest_path)}")
                            st.write(f"Risk sum: {fastest_risk:.3f}")
                            st.write(f"Top-10 hubs visited: {fastest_hubs}")
                            st.write(_fmt_path(fastest_path))
                        with col_rob:
                            st.markdown("**Robust**")
                            st.write(f"Total time: {_fmt_minutes(robust_time_sec)}")
                            st.write(f"Stops: {len(robust_path)}")
                            st.write(f"Risk sum: {robust_risk:.3f}")
                            st.write(f"Top-10 hubs visited: {robust_hubs}")
                            st.write(_fmt_path(robust_path))

                    if ENABLE_PAGERANK and top10:
                        st.markdown("**Top-10 hubs (PageRank)**")
                        hub_rows = []
                        pr_scores = pr
                        risk_scores = risk
                        for sid, score in top10.items():
                            info = node_info.get(sid)
                            hub_rows.append(
                                {
                                    "station_key": sid,
                                    "station_name": info.display_name if info else "",
                                    "pagerank_score": score,
                                    "risk": risk_scores.get(sid, 0.0),
                                }
                            )
                        st.dataframe(hub_rows, use_container_width=True)

    st.subheader("Local SPARQL Query")
    preset_stop_id = st.text_input("Stop ID for neighbors preset", value="100001")
    neighbor_query = NEIGHBORS_TEMPLATE.replace("%STOP_ID%", preset_stop_id.strip())
    preset_options = {
        "Stops basic": default_query,
        "Edges (top connections)": EDGES_SPARQL,
        "Neighbors for stop_id": neighbor_query,
    }
    preset_label = st.selectbox("Preset queries", options=list(preset_options.keys()), index=0)
    sparql_query = st.text_area("SPARQL query", value=preset_options[preset_label], height=220)

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
