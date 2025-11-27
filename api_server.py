from pathlib import Path
from typing import List

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import networkx as nx
from rdflib import Graph

DATA_DIR = Path(__file__).parent / "data"
KG_GLOB = "kg_gtfs_*.ttl"
DEMO_KG = DATA_DIR / "kg_demo.ttl"
CACHE_DIR = DATA_DIR / "cache"

app = FastAPI(title="Transport KG API", version="0.1.0")

# Allow local dev (Vite on 5173, etc.). For production, tighten this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

stops_cache: pd.DataFrame | None = None
kg_path_used: Path | None = None
edges_cache: pd.DataFrame | None = None
graph_cache: nx.DiGraph | None = None
stop_lookup: dict[str, dict] = {}


def stops_df_from_kg(kg: Graph) -> pd.DataFrame:
    """Extract stops from KG into a DataFrame."""
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
    rows: List[dict] = []
    for r in kg.query(query):
        rows.append(
            {
                "stop_id": str(r.s).rsplit("/stop/", 1)[-1],
                "stop_name": str(r.name) if getattr(r, "name", None) else "",
                "stop_lat": float(r.lat) if getattr(r, "lat", None) else 0.0,
                "stop_lon": float(r.lon) if getattr(r, "lon", None) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def pick_kg_path() -> Path:
    """Choose the best available KG cache."""
    kg_candidates = sorted(DATA_DIR.glob(KG_GLOB))
    if kg_candidates:
        return kg_candidates[-1]
    if DEMO_KG.exists():
        return DEMO_KG
    raise FileNotFoundError("No KG cache found. Please build the KG first.")


def load_stops() -> tuple[pd.DataFrame, Path]:
    kg_path = pick_kg_path()
    graph = Graph()
    graph.parse(kg_path, format="turtle")
    df = stops_df_from_kg(graph)
    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce")
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce")
    df = df.dropna(subset=["stop_lat", "stop_lon"])
    df = df[(df["stop_lat"] != 0.0) & (df["stop_lon"] != 0.0)]
    if df.empty:
        raise ValueError("No valid stops found in KG.")
    return df, kg_path


def load_edges_and_graph(stops_df: pd.DataFrame) -> tuple[pd.DataFrame | None, nx.DiGraph | None]:
    if not CACHE_DIR.exists():
        return None, None
    edge_files = sorted(CACHE_DIR.glob("edges_*.parquet"))
    graph_files = sorted(CACHE_DIR.glob("graph_*.pkl"))
    edges_df = None
    G = None
    if edge_files:
        edges_df = pd.read_parquet(edge_files[-1])
    if graph_files:
        try:
            import pickle

            with open(graph_files[-1], "rb") as f:
                G, _node_info = pickle.load(f)
        except Exception:
            G = None

    # Build graph if missing
    if G is None and edges_df is not None:
        G = nx.DiGraph()
        for row in edges_df.itertuples(index=False):
            src = str(getattr(row, "from_stop_id"))
            dst = str(getattr(row, "to_stop_id"))
            time_sec = float(getattr(row, "avg_travel_time_sec", 60.0) or 60.0)
            G.add_edge(src, dst, weight=time_sec)
    return edges_df, G


@app.on_event("startup")
def preload_data() -> None:
    global stops_cache, kg_path_used, edges_cache, graph_cache, stop_lookup
    df, path_used = load_stops()
    stops_cache = df
    kg_path_used = path_used
    # Build lookup for coords
    stop_lookup = {
        str(row.stop_id): {
            "lat": float(row.stop_lat),
            "lon": float(row.stop_lon),
            "name": str(row.stop_name) if row.stop_name else "",
        }
        for row in df.itertuples(index=False)
    }
    edges_cache, graph_cache = load_edges_and_graph(df)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stops_cached": 0 if stops_cache is None else len(stops_cache),
        "kg_path": str(kg_path_used) if kg_path_used else None,
        "edges_cached": 0 if edges_cache is None else len(edges_cache),
        "graph_loaded": graph_cache is not None,
    }


@app.get("/api/stops")
def get_stops() -> list[dict]:
    if stops_cache is None:
        raise HTTPException(status_code=503, detail="Stops not loaded")
    return stops_cache.to_dict(orient="records")


@app.get("/api/edges")
def get_edges() -> list[dict]:
    if edges_cache is None:
        raise HTTPException(status_code=503, detail="Edges not available")
    # attach coordinates for front-end
    records = []
    for row in edges_cache.itertuples(index=False):
        src = str(getattr(row, "from_stop_id"))
        dst = str(getattr(row, "to_stop_id"))
        src_info = stop_lookup.get(src)
        dst_info = stop_lookup.get(dst)
        if not src_info or not dst_info:
            continue
        records.append(
            {
                "from_stop_id": src,
                "to_stop_id": dst,
                "from_lat": src_info["lat"],
                "from_lon": src_info["lon"],
                "to_lat": dst_info["lat"],
                "to_lon": dst_info["lon"],
                "avg_travel_time_sec": float(getattr(row, "avg_travel_time_sec", 0.0) or 0.0),
                "trip_count": float(getattr(row, "trip_count", 0.0) or 0.0),
            }
        )
    return records


@app.get("/api/route")
def get_route(src: str, dst: str) -> dict:
    if graph_cache is None:
        raise HTTPException(status_code=503, detail="Graph not available")
    if src not in graph_cache or dst not in graph_cache:
        raise HTTPException(status_code=404, detail="Stop not in graph")
    try:
        path = nx.shortest_path(graph_cache, source=src, target=dst, weight="weight")
    except nx.NetworkXNoPath:
        raise HTTPException(status_code=404, detail="No path found")

    coords = []
    features_points = []
    for sid in path:
        info = stop_lookup.get(sid)
        if not info:
            continue
        coords.append([info["lon"], info["lat"]])
        features_points.append(
            {
                "type": "Feature",
                "properties": {"stop_id": sid, "stop_name": info["name"]},
                "geometry": {"type": "Point", "coordinates": [info["lon"], info["lat"]]},
            }
        )
    line_feature = {
        "type": "Feature",
        "properties": {"stop_ids": path},
        "geometry": {"type": "LineString", "coordinates": coords},
    }
    return {
        "type": "FeatureCollection",
        "features": [line_feature] + features_points,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
