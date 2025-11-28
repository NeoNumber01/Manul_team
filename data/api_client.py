import requests
import time
import json
import os
import polyline

class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"
        self.station_lookup = {}

        self.GERMANY_BOUNDS = {
            "lat_min": 47.0, "lat_max": 55.5,
            "lon_min": 5.5, "lon_max": 15.5
        }

        # Load station database
        self.load_station_database()

        # Load shapes cache
        self.shapes_cache = {}
        self.shapes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shapes_cache.json')
        self.load_shapes_cache()

        # Monitoring list (given by Chinese friend)
        self.target_stations = {
            "Heilbronn Hbf": "8000156",
            "Stuttgart Hbf": "8000096",
            "Frankfurt Hbf": "8000105",
            "Munich Hbf": "8000261",
            "Berlin Hbf": "8011160",
            "Hamburg Hbf": "8002549",
            "Mannheim Hbf": "8000244",
            "Nürnberg Hbf": "8000284",
            "Köln Hbf": "8000207",
            "Leipzig Hbf": "8010205",
            "Hannover Hbf": "8000152"
        }

    def load_station_database(self):
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stations_db.json')
            with open(path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            for name, coords in raw_data.items():
                if coords and len(coords) == 2:
                    if self.is_in_germany(coords[0], coords[1]):
                        self.station_lookup[name] = coords
        except Exception:
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
        return (
            self.GERMANY_BOUNDS["lat_min"] <= lat <= self.GERMANY_BOUNDS["lat_max"] and
            self.GERMANY_BOUNDS["lon_min"] <= lon <= self.GERMANY_BOUNDS["lon_max"]
        )

    def get_coords(self, name):
        if not name:
            return None
        if name in self.station_lookup:
            return self.station_lookup[name]
        clean = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for k, v in self.station_lookup.items():
            if clean in k:
                return v
        return None

    def get_trip_shape(self, trip_id, line_name, origin, destination):
        cache_key = f"{line_name}{origin}{destination}"

        if cache_key in self.shapes_cache:
            return self.shapes_cache[cache_key]

        try:
            time.sleep(0.25)
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=4)

            if res.status_code == 200:
                data = res.json()
                encoded = data.get('trip', {}).get('polyline')
                if encoded:
                    points = polyline.decode(encoded)
                    self.shapes_cache[cache_key] = points
                    self.save_shapes_cache()
                    return points
        except:
            return None

        return None

    def get_realtime_departures(self, station_id):
        try:
            origin_name = next((k for k, v in self.target_stations.items() if v == station_id), "Unknown")

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 120, "results": 20, "when": "now"}

            res = requests.get(url, params=params, timeout=4)
            if res.status_code != 200:
                return 0, []

            data = res.json()
            departures = data.get('departures', [])

            details = []
            delays = []

            for dep in departures:
                delay = dep.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)
                if not dest_coords:
                    continue

                line_name = dep.get('line', {}).get('name', '?')
                trip_id = dep.get('tripId')
                real_shape = None

                if trip_id:
                    real_shape = self.get_trip_shape(trip_id, line_name, origin_name, direction)

                details.append({
                    "line": line_name,
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape
                })

            avg = sum(delays) / len(delays) if delays else 0
            return avg, details

        except Exception as e:
            print(f"API Error: {e}")
            return 0, []
