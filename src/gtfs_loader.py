"""Load GTFS data from an uploaded ZIP."""

import io
import zipfile
from typing import Iterable, Optional

import pandas as pd


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in stops.txt: {', '.join(missing)}")
    return df[list(required)]


def load_stops_from_gtfs_zip(gtfs_zip_bytes: bytes) -> "pd.DataFrame":
    """Load stops.txt from a GTFS ZIP into a DataFrame with required columns."""
    with zipfile.ZipFile(io.BytesIO(gtfs_zip_bytes)) as zf:
        stop_entries = [name for name in zf.namelist() if name.lower().endswith("stops.txt")]
        if not stop_entries:
            raise ValueError("GTFS ZIP is missing stops.txt")
        stop_entry = stop_entries[0]
        with zf.open(stop_entry) as stops_file:
            df = pd.read_csv(stops_file)
    required_cols = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    df = _ensure_columns(df, required_cols)
    if "parent_station" not in df.columns:
        df["parent_station"] = None
    return df


def load_stop_times_from_gtfs_zip(gtfs_zip_bytes: bytes) -> pd.DataFrame:
    """Load stop_times.txt with essential columns; tolerate missing arrival/departure."""
    with zipfile.ZipFile(io.BytesIO(gtfs_zip_bytes)) as zf:
        entries = [name for name in zf.namelist() if name.lower().endswith("stop_times.txt")]
        if not entries:
            raise ValueError("GTFS ZIP is missing stop_times.txt")
        entry = entries[0]
        with zf.open(entry) as f:
            df = pd.read_csv(f)

    required = ["trip_id", "stop_id", "stop_sequence"]
    optional = ["arrival_time", "departure_time"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"stop_times.txt missing required column: {col}")
    for col in optional:
        if col not in df.columns:
            df[col] = None

    return df[required + optional]


def parse_gtfs_time_to_seconds(t: Optional[str]) -> Optional[int]:
    """Parse GTFS HH:MM:SS where hours may exceed 23; return seconds from midnight."""
    if t is None or not isinstance(t, str):
        return None
    t = t.strip()
    if not t:
        return None
    parts = t.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def build_station_lookup(stops_df: pd.DataFrame) -> dict[str, dict]:
    """Map stop_id to basic station metadata."""
    lookup: dict[str, dict] = {}
    for row in stops_df.itertuples(index=False):
        lookup[str(row.stop_id)] = {
            "stop_name": getattr(row, "stop_name", "") or "",
            "parent_station": getattr(row, "parent_station", None),
        }
    return lookup
