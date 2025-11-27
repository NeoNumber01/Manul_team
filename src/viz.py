"""Small helpers for mapping routes to coordinates and tables."""

import pandas as pd
import networkx as nx
import pydeck as pdk

GERMANY_BBOX = {
    "west": 5.866,
    "south": 47.270,
    "east": 15.041,
    "north": 55.099,
}
GERMANY_CENTER = {"lat": 51.1657, "lon": 10.4515}
GERMANY_DEFAULT_ZOOM = 6.2
MIN_ZOOM_ALLOWED = 6.0
MAX_ZOOM_ALLOWED = 13.5


def build_stop_lookup(stops_df: pd.DataFrame) -> dict[str, dict]:
    """Return stop_id -> metadata lookup for quick coordinate access."""
    lookup = {}
    for row in stops_df.itertuples(index=False):
        lat = getattr(row, "stop_lat", None)
        lon = getattr(row, "stop_lon", None)
        if lat is None or lon is None:
            continue
        try:
            lat_val = float(lat)
            lon_val = float(lon)
        except (TypeError, ValueError):
            continue
        if pd.isna(lat_val) or pd.isna(lon_val):
            continue
        lookup[str(row.stop_id)] = {"name": getattr(row, "stop_name", "") or "", "lat": lat_val, "lon": lon_val}
    return lookup


def path_to_points_df(path_nodes: list[str], node_to_stop_id: dict[str, str], stop_lookup: dict[str, dict]) -> pd.DataFrame:
    """Convert a path of graph nodes into a points DataFrame with coords."""
    rows = []
    for idx, node in enumerate(path_nodes):
        stop_id = node_to_stop_id.get(node)
        meta = stop_lookup.get(stop_id or "")
        if not meta:
            continue
        rows.append(
            {
                "idx": idx,
                "node_key": node,
                "stop_id": stop_id,
                "name": meta.get("name", ""),
                "lat": meta["lat"],
                "lon": meta["lon"],
                "is_start": idx == 0,
                "is_end": idx == len(path_nodes) - 1,
            }
        )
    return pd.DataFrame(rows)


def path_to_line_df(points_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare a single-row dataframe for PyDeck PathLayer."""
    if points_df.empty:
        return pd.DataFrame([{"path": [], "color": [30, 120, 200, 200]}])
    path = points_df.sort_values("idx")[["lon", "lat"]].values.tolist()
    return pd.DataFrame([{"path": path, "color": [30, 120, 200, 200]}])


def build_legs_df(G: nx.DiGraph, path_nodes: list[str], node_info: dict[str, any]) -> pd.DataFrame:
    """Create a leg-by-leg table from a path."""
    rows = []
    cumulative = 0.0
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i + 1]
        data = G.get_edge_data(u, v, default={})
        leg_sec = float(data.get("time_sec", 60.0))
        cumulative += leg_sec
        rows.append(
            {
                "leg_index": i,
                "from_node": u,
                "to_node": v,
                "from_name": getattr(node_info.get(u), "display_name", "") if node_info else "",
                "to_name": getattr(node_info.get(v), "display_name", "") if node_info else "",
                "leg_time_sec": leg_sec,
                "cumulative_time_sec": cumulative,
                "leg_time_min": leg_sec / 60.0,
                "cumulative_time_min": cumulative / 60.0,
            }
        )
    return pd.DataFrame(rows)


def compute_view_state(points_df: pd.DataFrame) -> pdk.ViewState:
    """Compute a view centered on Germany, clamping to a DE bounding box."""
    df = points_df.copy()
    if df.empty:
        return pdk.ViewState(
            latitude=GERMANY_CENTER["lat"],
            longitude=GERMANY_CENTER["lon"],
            zoom=GERMANY_DEFAULT_ZOOM,
            min_zoom=MIN_ZOOM_ALLOWED,
            max_zoom=MAX_ZOOM_ALLOWED,
        )

    df = df.dropna(subset=["lat", "lon"])
    if df.empty:
        return pdk.ViewState(
            latitude=GERMANY_CENTER["lat"],
            longitude=GERMANY_CENTER["lon"],
            zoom=GERMANY_DEFAULT_ZOOM,
            min_zoom=MIN_ZOOM_ALLOWED,
            max_zoom=MAX_ZOOM_ALLOWED,
        )

    df_in_de = filter_points_to_germany(df)
    if len(df_in_de) < 2:
        return pdk.ViewState(
            latitude=GERMANY_CENTER["lat"],
            longitude=GERMANY_CENTER["lon"],
            zoom=GERMANY_DEFAULT_ZOOM,
            min_zoom=MIN_ZOOM_ALLOWED,
            max_zoom=MAX_ZOOM_ALLOWED,
        )

    min_lat, max_lat = df_in_de["lat"].min(), df_in_de["lat"].max()
    min_lon, max_lon = df_in_de["lon"].min(), df_in_de["lon"].max()
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    span = max(max_lon - min_lon, max_lat - min_lat)
    if span < 0.02:
        zoom = 13
    elif span < 0.05:
        zoom = 12
    elif span < 0.1:
        zoom = 11
    elif span < 0.2:
        zoom = 10
    else:
        zoom = 8
    center_lat, center_lon = clamp_to_germany(center_lat, center_lon)
    zoom = max(MIN_ZOOM_ALLOWED, min(zoom, MAX_ZOOM_ALLOWED))
    return pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        min_zoom=MIN_ZOOM_ALLOWED,
        max_zoom=MAX_ZOOM_ALLOWED,
    )


def is_in_germany(lat: float, lon: float) -> bool:
    """Return True if coordinate is inside Germany bounding box."""
    return (
        GERMANY_BBOX["south"] <= lat <= GERMANY_BBOX["north"]
        and GERMANY_BBOX["west"] <= lon <= GERMANY_BBOX["east"]
    )


def clamp_to_germany(lat: float, lon: float) -> tuple[float, float]:
    """Clamp coordinates into Germany bounding box."""
    clamped_lat = min(max(lat, GERMANY_BBOX["south"]), GERMANY_BBOX["north"])
    clamped_lon = min(max(lon, GERMANY_BBOX["west"]), GERMANY_BBOX["east"])
    return clamped_lat, clamped_lon


def filter_points_to_germany(points_df: pd.DataFrame) -> pd.DataFrame:
    """Filter points to those within Germany; drop rows with invalid coords."""
    if points_df.empty:
        return points_df
    df = points_df.dropna(subset=["lat", "lon"]).copy()
    df = df[df.apply(lambda r: is_in_germany(r.lat, r.lon), axis=1)]
    return df
