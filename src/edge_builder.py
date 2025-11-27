"""Compute stop-to-stop edges and summary stats from GTFS stop_times."""

from pathlib import Path

import pandas as pd

from src.gtfs_loader import parse_gtfs_time_to_seconds


def _compute_travel_seconds(curr_departure: str | None, next_arrival: str | None) -> float | None:
    depart_sec = parse_gtfs_time_to_seconds(curr_departure)
    arrive_sec = parse_gtfs_time_to_seconds(next_arrival)
    if depart_sec is None or arrive_sec is None:
        return None
    delta = arrive_sec - depart_sec
    if delta < 0:
        return None
    return float(delta)


def build_edge_stats(stop_times_df: pd.DataFrame, *, max_trips: int | None = None) -> pd.DataFrame:
    """Build directed edge aggregates between consecutive stops per trip."""
    if max_trips is not None and max_trips > 0:
        keep_trips = stop_times_df["trip_id"].drop_duplicates().head(max_trips)
        stop_times_df = stop_times_df[stop_times_df["trip_id"].isin(keep_trips)].copy()
    else:
        stop_times_df = stop_times_df.copy()

    sort_cols = ["trip_id", "stop_sequence"]
    stop_times_df = stop_times_df.sort_values(sort_cols)

    grouped = stop_times_df.groupby("trip_id", sort=False)
    stop_times_df["next_stop_id"] = grouped["stop_id"].shift(-1)
    stop_times_df["next_arrival_time"] = grouped["arrival_time"].shift(-1)

    def choose_departure(row):
        dep = row.get("departure_time")
        if pd.isna(dep):
            return row.get("arrival_time")
        return dep

    stop_times_df["curr_departure_time"] = stop_times_df.apply(choose_departure, axis=1)
    stop_times_df["travel_time_sec"] = stop_times_df.apply(
        lambda r: _compute_travel_seconds(r["curr_departure_time"], r["next_arrival_time"]), axis=1
    )

    edges = stop_times_df.dropna(subset=["next_stop_id"])[
        ["stop_id", "next_stop_id", "travel_time_sec"]
    ].rename(columns={"stop_id": "from_stop_id", "next_stop_id": "to_stop_id"})

    edges["travel_time_sec"] = pd.to_numeric(edges["travel_time_sec"], errors="coerce")

    grouped = edges.groupby(["from_stop_id", "to_stop_id"], as_index=False)
    grouped_edges = grouped.agg(
        trip_count=("travel_time_sec", "size"),
        avg_travel_time_sec=("travel_time_sec", "mean"),
    )

    return grouped_edges


def save_edges_cache(edges_df: pd.DataFrame, cache_path: Path) -> None:
    """Save aggregated edges to cache (Parquet if available, else CSV)."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.suffix == ".parquet":
        try:
            edges_df.to_parquet(cache_path, index=False)
            return
        except Exception:
            # Fall back to CSV next to the parquet path.
            csv_path = cache_path.with_suffix(".csv")
            edges_df.to_csv(csv_path, index=False)
            return
    edges_df.to_csv(cache_path, index=False)


def load_edges_cache(cache_path: Path) -> pd.DataFrame | None:
    """Load cached edges if present; return None when missing."""
    if cache_path.suffix == ".parquet":
        if cache_path.exists():
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass
        csv_path = cache_path.with_suffix(".csv")
        if csv_path.exists():
            return pd.read_csv(csv_path)
        return None
    if not cache_path.exists():
        return None
    return pd.read_csv(cache_path)
