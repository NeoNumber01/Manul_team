from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import polyline
import requests

# Shared data directory for caches and station metadata
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class TransportAPI:
    """Thin wrapper around the db.transport.rest API with local caching for station coords and trip shapes."""

    def __init__(self) -> None:
        self.base_url = "https://v6.db.transport.rest"
        self.station_lookup: Dict[str, List[float]] = {}

        # Germany bounds for sanity checks
        self.GERMANY_BOUNDS = {"lat_min": 47.0, "lat_max": 55.5, "lon_min": 5.5, "lon_max": 15.5}

        # Load station coordinates
        self.load_station_database()
        self.ensure_core_stations_exist()

        # Local cache for trip shapes (persisted as shapes_cache.json)
        self.shapes_cache: Dict[str, List[Tuple[float, float]]] = {}
        self.shapes_file = DATA_DIR / "shapes_cache.json"
        self.load_shapes_cache()

        # Cache for rail line segments (origin -> destination) to avoid re-downloading shapes
        self.lines_cache: Dict[str, list] = {}
        self.lines_file = DATA_DIR / "lines_cache.json"
        self.load_lines_cache()

        # Monitored hubs (name -> station id)
        self.target_stations = {
            "Heilbronn Hbf": "8000156",
            "Stuttgart Hbf": "8000096",
            "Munich Hbf": "8000261",
            "Frankfurt Hbf": "8000105",
            "Berlin Hbf": "8011160",
            "Hamburg Hbf": "8002549",
            "Köln Hbf": "8000207",
            "Mannheim Hbf": "8000244",
            "Karlsruhe Hbf": "8000191",
            "Nürnberg Hbf": "8000284",
            "Leipzig Hbf": "8010205",
            "Hannover Hbf": "8000152",
            "Düsseldorf Hbf": "8000085",
            "Dortmund Hbf": "8000080",
            "Essen Hbf": "8000098",
            "Bremen Hbf": "8000050",
            "Dresden Hbf": "8010085",
            "Mainz Hbf": "8000240",
            "Freiburg Hbf": "8000107",
            "Ulm Hbf": "8000170",
            "Würzburg Hbf": "8000260",
            "Erfurt Hbf": "8010101",
            "Kiel Hbf": "8000199",
            "Kassel-Wilhelmshöhe": "8003200",
            "Fulda": "8000115",
            "Augsburg Hbf": "8000013",
        }

    def load_station_database(self) -> None:
        """Load station coordinates from a bundled JSON file."""
        path = DATA_DIR / "stations_db.json"
        if not path.exists():
            self.station_lookup = {}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for name, coords in raw_data.items():
                if coords and len(coords) == 2:
                    lat, lon = coords
                    if self.is_in_germany(lat, lon):
                        self.station_lookup[name] = coords
        except Exception:
            self.station_lookup = {}

    def ensure_core_stations_exist(self) -> None:
        """Force insert critical stations to handle naming mismatches."""
        fallback_coords = {
            "Munich Hbf": (48.1403, 11.5588),
            "München Hbf": (48.1403, 11.5588),
            "Nürnberg Hbf": (49.4456, 11.0829),
            "Nuremberg Hbf": (49.4456, 11.0829),
            "Frankfurt Hbf": (50.1071, 8.6638),
            "Frankfurt(Main)Hbf": (50.1071, 8.6638),
            "Köln Hbf": (50.9432, 6.9586),
            "Cologne Hbf": (50.9432, 6.9586),
        }
        for name, coords in fallback_coords.items():
            if name not in self.station_lookup:
                self.station_lookup[name] = coords

    def load_shapes_cache(self) -> None:
        """Load previously persisted trip shapes."""
        if not self.shapes_file.exists():
            return
        try:
            with open(self.shapes_file, "r", encoding="utf-8") as f:
                self.shapes_cache = json.load(f)
        except Exception:
            self.shapes_cache = {}

    def save_shapes_cache(self) -> None:
        """Persist trip shapes to disk."""
        try:
            with open(self.shapes_file, "w", encoding="utf-8") as f:
                json.dump(self.shapes_cache, f)
        except Exception:
            # Cache persistence failure should not break the app
            pass

    def load_lines_cache(self) -> None:
        """Load cached rail lines (origin->destination) to reuse without re-download."""
        if not self.lines_file.exists():
            return
        try:
            with open(self.lines_file, "r", encoding="utf-8") as f:
                self.lines_cache = json.load(f)
        except Exception:
            self.lines_cache = {}

    def save_lines_cache(self) -> None:
        """Persist cached rail lines to disk."""
        try:
            with open(self.lines_file, "w", encoding="utf-8") as f:
                json.dump(self.lines_cache, f)
        except Exception:
            pass

    def _cache_line_segment(
        self, origin: str, destination: str, origin_coords: list[float] | None, dest_coords: list[float] | None, shape
    ) -> None:
        """Store a reusable line (real shape preferred; fallback to straight line)."""
        if not destination:
            return
        key = f"{origin}->{destination}"
        if shape:
            self.lines_cache[key] = shape
        elif origin_coords and dest_coords:
            self.lines_cache[key] = [[origin_coords[0], origin_coords[1]], [dest_coords[0], dest_coords[1]]]
        else:
            return
        self.save_lines_cache()

    def get_cached_line(self, origin: str, destination: str) -> list | None:
        key = f"{origin}->{destination}"
        return self.lines_cache.get(key)

    def is_in_germany(self, lat: float, lon: float) -> bool:
        return (
            self.GERMANY_BOUNDS["lat_min"] <= lat <= self.GERMANY_BOUNDS["lat_max"]
            and self.GERMANY_BOUNDS["lon_min"] <= lon <= self.GERMANY_BOUNDS["lon_max"]
        )

    def get_coords(self, name: str) -> List[float] | None:
        """Resolve station name to coordinates with light fuzzy matching."""
        if not name:
            return None
        if name in self.station_lookup:
            return self.station_lookup[name]
        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for station_name, coords in self.station_lookup.items():
            if clean_name in station_name:
                return coords
        return None

    def get_trip_shape(self, trip_id: str, line_name: str, origin: str, destination: str):
        """
        Fetch a trip polyline from the API with local caching.
        Key excludes trip_id to reuse shapes across days.
        """
        cache_key = f"{line_name}_{origin}_{destination}"

        # 1) Serve from cache if available
        if cache_key in self.shapes_cache:
            return self.shapes_cache[cache_key]

        # 2) Otherwise fetch from API
        try:
            time.sleep(0.25)  # throttle slightly
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=5)
            res.raise_for_status()

            data = res.json()
            encoded = data.get("trip", {}).get("polyline")
            if encoded:
                points = polyline.decode(encoded)
                self.shapes_cache[cache_key] = points
                self.save_shapes_cache()
                return points
        except Exception:
            return None

        return None

    def _fetch_single_shape(self, trip_id: str) -> list | None:
        """Fetch one trip polyline (used for concurrent downloads)."""
        try:
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=5)
            res.raise_for_status()
            data = res.json()
            encoded = data.get("trip", {}).get("polyline")
            if encoded:
                return polyline.decode(encoded)
        except Exception:
            return None
        return None

    def get_realtime_departures(self, station_id: str) -> tuple[float, list[dict]]:
        """Return average delay and departure details for a station with concurrency and caching."""
        try:
            origin_name = next((name for name, sid in self.target_stations.items() if sid == station_id), "Unknown")
            origin_coords = self.get_coords(origin_name)

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 60, "results": 50, "when": "now"}
            res = requests.get(url, params=params, timeout=8)
            if res.status_code != 200:
                return 0, []

            data = res.json()
            departures = data.get("departures", [])

            delays: list[float] = []
            temp_results: list[dict | None] = [None] * len(departures)
            tasks: list[tuple[int, str, str]] = []  # (index, trip_id, cache_key)

            for i, dep in enumerate(departures):
                delay = dep.get("delay", 0) or 0
                # Treat early departures (negative delay) as on time
                delay_min = max(delay, 0) / 60
                delays.append(delay_min)

                direction = dep.get("direction", "Unknown")
                dest_coords = self.get_coords(direction)
                if not dest_coords:
                    continue

                trip_id = dep.get("tripId")
                line_name = dep.get("line", {}).get("name", "?")
                cache_key = f"{line_name}_{origin_name}_{direction}"

                real_shape = None
                if cache_key in self.shapes_cache:
                    real_shape = self.shapes_cache[cache_key]
                elif trip_id:
                    tasks.append((i, trip_id, cache_key))

                cached_shape = self.get_cached_line(origin_name, direction)

                temp_results[i] = {
                    "line": line_name,
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape,
                    "cached_shape": cached_shape,
                }

            # Concurrently fetch missing shapes
            if tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_map = {executor.submit(self._fetch_single_shape, trip_id): (idx, cache_key) for idx, trip_id, cache_key in tasks}
                    for future in as_completed(future_map):
                        idx, cache_key = future_map[future]
                        shape = future.result()
                        if shape:
                            if temp_results[idx]:
                                temp_results[idx]["real_shape"] = shape
                                temp_results[idx]["cached_shape"] = temp_results[idx].get("cached_shape") or shape
                            self.shapes_cache[cache_key] = shape
                self.save_shapes_cache()

            # Persist line cache for future runs
            for entry in temp_results:
                if not entry:
                    continue
                self._cache_line_segment(
                    origin_name,
                    entry["to"],
                    origin_coords,
                    entry["dest_coords"],
                    entry.get("real_shape") or entry.get("cached_shape"),
                )

            # Keep only valid entries and sort by delay descending to surface delayed trips first
            details = sorted([x for x in temp_results if x is not None], key=lambda r: r["delay"], reverse=True)
            avg_delay = sum(delays) / len(delays) if delays else 0
            return avg_delay, details
        except Exception:
            return 0, []

    def get_realtime_arrivals(self, station_id: str) -> tuple[float, list[dict]]:
        """Return average delay and arrival details for a station (incoming trains)."""
        try:
            station_name = next((name for name, sid in self.target_stations.items() if sid == station_id), "Unknown")
            station_coords = self.get_coords(station_name)

            url = f"{self.base_url}/stops/{station_id}/arrivals"
            params = {"duration": 60, "results": 50, "when": "now"}
            res = requests.get(url, params=params, timeout=8)
            if res.status_code != 200:
                return 0, []

            data = res.json()
            arrivals = data.get("arrivals", [])

            delays: list[float] = []
            temp_results: list[dict | None] = [None] * len(arrivals)
            tasks: list[tuple[int, str, str]] = []

            for i, arr in enumerate(arrivals):
                delay_raw = arr.get("delay")
                if delay_raw is None:
                    delay_raw = arr.get("arrivalDelay", 0)
                delay_min = max(delay_raw or 0, 0) / 60
                delays.append(delay_min)

                origin = arr.get("provenance") or arr.get("origin") or arr.get("direction") or "Unknown"
                origin_coords = self.get_coords(origin)
                if not origin_coords:
                    continue

                trip_id = arr.get("tripId")
                line_name = arr.get("line", {}).get("name", "?")
                cache_key = f"{line_name}_{origin}_{station_name}"

                real_shape = None
                if cache_key in self.shapes_cache:
                    real_shape = self.shapes_cache[cache_key]
                elif trip_id:
                    tasks.append((i, trip_id, cache_key))

                cached_shape = self.get_cached_line(origin, station_name)

                temp_results[i] = {
                    "line": line_name,
                    "origin": origin,
                    "delay": delay_min,
                    "origin_coords": origin_coords,
                    "dest_coords": station_coords,
                    "real_shape": real_shape,
                    "cached_shape": cached_shape,
                }

            if tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_map = {executor.submit(self._fetch_single_shape, trip_id): (idx, cache_key) for idx, trip_id, cache_key in tasks}
                    for future in as_completed(future_map):
                        idx, cache_key = future_map[future]
                        shape = future.result()
                        if shape:
                            if temp_results[idx]:
                                temp_results[idx]["real_shape"] = shape
                                temp_results[idx]["cached_shape"] = temp_results[idx].get("cached_shape") or shape
                            self.shapes_cache[cache_key] = shape
                self.save_shapes_cache()

            for entry in temp_results:
                if not entry:
                    continue
                self._cache_line_segment(
                    entry["origin"],
                    station_name,
                    entry.get("origin_coords"),
                    station_coords,
                    entry.get("real_shape") or entry.get("cached_shape"),
                )

            details = sorted([x for x in temp_results if x is not None], key=lambda r: r["delay"], reverse=True)
            avg_delay = sum(delays) / len(delays) if delays else 0
            return avg_delay, details
        except Exception:
            return 0, []
