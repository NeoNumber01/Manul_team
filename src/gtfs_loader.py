"""Load GTFS data from an uploaded ZIP."""

import io
import zipfile
from typing import Iterable

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
    return _ensure_columns(df, required_cols)
