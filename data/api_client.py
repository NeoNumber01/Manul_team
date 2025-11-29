import requests
import time
import json
import os
import polyline
from concurrent.futures import ThreadPoolExecutor, as_completed


class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"
        self.station_lookup = {}

        self.GERMANY_BOUNDS = {
            "lat_min": 47.0, "lat_max": 55.5,
            "lon_min": 5.5, "lon_max": 15.5
        }

        self.load_station_database()
        self.ensure_core_stations_exist()

        self.shapes_cache = {}
        self.shapes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shapes_cache.json')
        self.load_shapes_cache()

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
            "Augsburg Hbf": "8000013"
        }

    # -------------------------------------------------------------
    # INTERPOLATION FUNCTION (CÁCH 3)
    # -------------------------------------------------------------
    def interpolate_current_position(self, real_shape, eta_timestamp):
        """
        Cách 3: Dự đoán vị trí hiện tại của tàu dựa trên thời gian còn lại + polyline.
        Nếu API không cung cấp đầy đủ thời gian → fallback linear interpolation.
        """
        if not real_shape or len(real_shape) < 2:
            return None

        if not eta_timestamp:
            # không có ETA → lấy 80% tuyến đường
            idx = int(0.8 * (len(real_shape) - 1))
            return real_shape[idx]

        now = time.time()
        remaining = eta_timestamp / 1000 - now  # DB REST uses ms

        if remaining <= 0:
            # tàu chuẩn bị vào ga → vị trí gần cuối polyline
            return real_shape[-2]

        # Assume whole trip ~ 40 minutes if unknown
        total_guess_seconds = 40 * 60  
        progress = 1 - min(remaining / total_guess_seconds, 1)
        index = int(progress * (len(real_shape) - 1))
        index = max(0, min(index, len(real_shape) - 1))
        return real_shape[index]

    # -------------------------------------------------------------

    def ensure_core_stations_exist(self):
        fallback_coords = {
            "Munich Hbf": (48.1403, 11.5588),
            "München Hbf": (48.1403, 11.5588),
            "Nürnberg Hbf": (49.4456, 11.0829),
            "Nuremberg Hbf": (49.4456, 11.0829),
            "Frankfurt Hbf": (50.1071, 8.6638),
            "Frankfurt(Main)Hbf": (50.1071, 8.6638),
            "Köln Hbf": (50.9432, 6.9586),
            "Cologne Hbf": (50.9432, 6.9586)
        }
        for name, coords in fallback_coords.items():
            if name not in self.station_lookup:
                self.station_lookup[name] = coords

    def load_station_database(self):
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stations_db.json')
            with open(path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            for name, coords in raw_data.items():
                if coords and len(coords) == 2:
                    if self.is_in_germany(coords[0], coords[1]):
                        self.station_lookup[name] = coords
        except:
            self.station_lookup = {}

    def load_shapes_cache(self):
        if os.path.exists(self.shapes_file):
            try:
                with open(self.shapes_file, 'r', encoding='utf-8') as f:
                    self.shapes_cache = json.load(f)
            except:
                self.shapes_cache = {}

    def save_shapes_cache(self):
        try:
            with open(self.shapes_file, 'w', encoding='utf-8') as f:
                json.dump(self.shapes_cache, f)
        except:
            pass

    def is_in_germany(self, lat, lon):
        return (self.GERMANY_BOUNDS["lat_min"] <= lat <= self.GERMANY_BOUNDS["lat_max"] and
                self.GERMANY_BOUNDS["lon_min"] <= lon <= self.GERMANY_BOUNDS["lon_max"])

    def get_coords(self, name):
        if not name:
            return None

        if name in self.station_lookup:
            return self.station_lookup[name]

        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for k, v in self.station_lookup.items():
            if clean_name in k:
                return v
        return None

    def _fetch_single_shape(self, trip_id):
        try:
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                encoded = data.get('trip', {}).get('polyline')
                if encoded:
                    return polyline.decode(encoded)
            return None
        except:
            return None

    # -------------------------------------------------------------
    # DEPARTURES
    # -------------------------------------------------------------
    def get_realtime_departures(self, station_id):
        try:
            origin_name = next((k for k, v in self.target_stations.items() if v == station_id), "Unknown")

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 60, "results": 5, "when": "now"}

            res = requests.get(url, params=params, timeout=4)
            if res.status_code != 200:
                return 0, []

            data = res.json()
            departures = data.get('departures', [])

            delays = []
            tasks = []
            temp_results = [None] * len(departures)

            for i, dep in enumerate(departures):
                delay = dep.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)

                if not dest_coords:
                    continue

                trip_id = dep.get('tripId')
                line_name = dep.get('line', {}).get('name', '?')
                cache_key = f"{line_name}_{origin_name}_{direction}"
                real_shape = self.shapes_cache.get(cache_key)

                if not real_shape and trip_id:
                    tasks.append((i, trip_id, cache_key))

                # INTERPOLATE CURRENT POSITION
                eta_timestamp = dep.get('when', None)
                current_pos = self.interpolate_current_position(real_shape, eta_timestamp)

                temp_results[i] = {
                    "line": line_name,
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape,
                    "current_coords": current_pos
                }

            if tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_info = {executor.submit(self._fetch_single_shape, t[1]): t for t in tasks}
                    for future in as_completed(future_to_info):
                        idx, trip_id, cache_key = future_to_info[future]
                        shape = future.result()
                        if shape:
                            temp_results[idx]["real_shape"] = shape
                            self.shapes_cache[cache_key] = shape

            self.save_shapes_cache()

            details = [x for x in temp_results if x is not None]
            avg_delay = sum(delays) / len(delays) if delays else 0
            return avg_delay, details

        except:
            return 0, []

    # -------------------------------------------------------------
    # ARRIVALS
    # -------------------------------------------------------------
    def get_realtime_arrivals(self, station_id):
        try:
            origin_name = next((k for k, v in self.target_stations.items() if v == station_id), "Unknown")

            url = f"{self.base_url}/stops/{station_id}/arrivals"
            params = {"duration": 60, "results": 5, "when": "now"}

            res = requests.get(url, params=params, timeout=4)
            if res.status_code != 200:
                return 0, []

            data = res.json()
            arrivals = data.get('arrivals', [])

            delays = []
            tasks = []
            temp_results = [None] * len(arrivals)

            for i, arr in enumerate(arrivals):
                delay = arr.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                origin = arr.get('provenance') or arr.get('origin') or 'Unknown'
                origin_coords = self.get_coords(origin)

                if not origin_coords:
                    direction = arr.get('direction')
                    if direction:
                        origin_coords = self.get_coords(direction)

                if not origin_coords:
                    continue

                trip_id = arr.get('tripId')
                line_name = arr.get('line', {}).get('name', '?')
                cache_key = f"{line_name}_{origin}_{origin_name}"

                real_shape = self.shapes_cache.get(cache_key)

                if not real_shape and trip_id:
                    tasks.append((i, trip_id, cache_key))

                # INTERPOLATE CURRENT POSITION
                eta_timestamp = arr.get('when', None)
                current_pos = self.interpolate_current_position(real_shape, eta_timestamp)

                temp_results[i] = {
                    "line": line_name,
                    "from": origin,
                    "delay": delay_min,
                    "origin_coords": origin_coords,
                    "real_shape": real_shape,
                    "current_coords": current_pos
                }

            if tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_info = {executor.submit(self._fetch_single_shape, t[1]): t for t in tasks}
                    for future in as_completed(future_to_info):
                        idx, trip_id, cache_key = future_to_info[future]
                        shape = future.result()
                        if shape:
                            temp_results[idx]["real_shape"] = shape
                            self.shapes_cache[cache_key] = shape

            self.save_shapes_cache()

            details = [x for x in temp_results if x is not None]
            avg_delay = sum(delays) / len(delays) if delays else 0
            return avg_delay, details

        except:
            return 0, []
        
def interpolate_on_line(start, end, progress):
    """
    start, end: [lat, lon]
    progress: float từ 0.0 → 1.0 (tỉ lệ tiến độ chuyến đi)
    """
    lat = start[0] + (end[0] - start[0]) * progress
    lon = start[1] + (end[1] - start[1]) * progress
    return [lat, lon]

import time

def compute_progress(dep_time=None, eta_timestamp=None, total_trip_seconds=2400):
    now = time.time()

    # Nếu timestamp đến là ms → chuyển sang giây
    if eta_timestamp and eta_timestamp > 1e12:  # > 1 trillion → ms
        eta_timestamp /= 1000

    if dep_time and eta_timestamp:
        total_seconds = eta_timestamp - dep_time
        elapsed = now - dep_time
        progress = min(max(elapsed / total_seconds, 0), 1)
        return progress

    if eta_timestamp:
        remaining = eta_timestamp - now
        progress = 1 - min(max(remaining / total_trip_seconds, 0), 1)
        return progress

    return 0.5



