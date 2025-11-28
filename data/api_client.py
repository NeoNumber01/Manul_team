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

        # 德国边界
        self.GERMANY_BOUNDS = {
            "lat_min": 47.0, "lat_max": 55.5,
            "lon_min": 5.5, "lon_max": 15.5
        }

        # 1. 加载本地数据库
        self.load_station_database()

        # 2. 强制补充核心城市坐标 (防止因中德文名不匹配导致的大站丢失)
        # 这就是修复慕尼黑消失的关键！
        self.ensure_core_stations_exist()

        # 3. 加载形状缓存
        self.shapes_cache = {}
        self.shapes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shapes_cache.json')
        self.load_shapes_cache()

        # 4. 监控列表
        self.target_stations = {
            "Heilbronn Hbf": "8000156",
            "Stuttgart Hbf": "8000096",
            "Munich Hbf": "8000261",  # 现在它一定能找到坐标了
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

    def ensure_core_stations_exist(self):
        """
        强制注入重要城市的坐标，作为最后的保险。
        解决 Munich vs München, Nuremberg vs Nürnberg 等命名问题。
        """
        fallback_coords = {
            "Munich Hbf": (48.1403, 11.5588),  # 解决 Munich 丢失
            "München Hbf": (48.1403, 11.5588),
            "Nürnberg Hbf": (49.4456, 11.0829),
            "Nuremberg Hbf": (49.4456, 11.0829),
            "Frankfurt Hbf": (50.1071, 8.6638),
            "Frankfurt(Main)Hbf": (50.1071, 8.6638),
            "Köln Hbf": (50.9432, 6.9586),
            "Cologne Hbf": (50.9432, 6.9586)
        }
        # 如果查找表里没有，就硬塞进去
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
        if not name: return None
        # 1. 精确匹配
        if name in self.station_lookup: return self.station_lookup[name]

        # 2. 模糊匹配 (去后缀)
        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for k, v in self.station_lookup.items():
            if clean_name in k: return v
        return None

    def _fetch_single_shape(self, trip_id):
        try:
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                encoded = data.get('trip', {}).get('polyline')
                if encoded: return polyline.decode(encoded)
            return None
        except:
            return None

    def get_realtime_departures(self, station_id):
        try:
            origin_name = "Unknown"
            for k, v in self.target_stations.items():
                if v == station_id: origin_name = k; break

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 60, "results": 5, "when": "now"}

            res = requests.get(url, params=params, timeout=4)
            if res.status_code != 200: return 0, []

            data = res.json()
            departures = data.get('departures', [])

            details = []
            delays = []
            tasks = []
            temp_results = [None] * len(departures)

            for i, dep in enumerate(departures):
                delay = dep.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)

                if not dest_coords: continue

                trip_id = dep.get('tripId')
                line_name = dep.get('line', {}).get('name', '?')
                cache_key = f"{line_name}_{origin_name}_{direction}"
                real_shape = None

                if cache_key in self.shapes_cache:
                    real_shape = self.shapes_cache[cache_key]
                elif trip_id:
                    tasks.append((i, trip_id, cache_key))

                temp_results[i] = {
                    "line": line_name,
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape
                }

            if tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_info = {executor.submit(self._fetch_single_shape, t[1]): t for t in tasks}
                    for future in as_completed(future_to_info):
                        idx, trip_id, cache_key = future_to_info[future]
                        shape = future.result()
                        if shape:
                            if temp_results[idx]: temp_results[idx]['real_shape'] = shape
                            self.shapes_cache[cache_key] = shape

                self.save_shapes_cache()

            details = [x for x in temp_results if x is not None]
            avg = sum(delays) / len(delays) if delays else 0
            return avg, details

        except Exception as e:
            return 0, []