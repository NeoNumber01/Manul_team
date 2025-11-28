import requests
import time
import json
import os
import polyline


class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"
        self.station_lookup = {}

        # 德国边界
        self.GERMANY_BOUNDS = {
            "lat_min": 47.0, "lat_max": 55.5,
            "lon_min": 5.5, "lon_max": 15.5
        }

        # 1. 加载站点坐标库 (stations_db.json)
        self.load_station_database()

        # 2. 加载路线形状缓存 (shapes_cache.json)
        # 这是我们新增的"黑科技"，用来存铁轨形状
        self.shapes_cache = {}
        self.shapes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shapes_cache.json')
        self.load_shapes_cache()

        # 监控列表
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
        """加载站点坐标"""
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
        """加载本地已保存的路线形状"""
        if os.path.exists(self.shapes_file):
            try:
                with open(self.shapes_file, 'r', encoding='utf-8') as f:
                    self.shapes_cache = json.load(f)
                print(f"📂 已加载本地路线缓存: {len(self.shapes_cache)} 条线路")
            except:
                self.shapes_cache = {}
        else:
            print("ℹ️ 本地无路线缓存，将从 API 获取并创建...")

    def save_shapes_cache(self):
        """把新抓到的路线保存到硬盘"""
        try:
            with open(self.shapes_file, 'w', encoding='utf-8') as f:
                json.dump(self.shapes_cache, f)
        except Exception as e:
            print(f"缓存保存失败: {e}")

    def is_in_germany(self, lat, lon):
        return (self.GERMANY_BOUNDS["lat_min"] <= lat <= self.GERMANY_BOUNDS["lat_max"] and
                self.GERMANY_BOUNDS["lon_min"] <= lon <= self.GERMANY_BOUNDS["lon_max"])

    def get_coords(self, name):
        if not name: return None
        if name in self.station_lookup: return self.station_lookup[name]
        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for k, v in self.station_lookup.items():
            if clean_name in k: return v
        return None

    def get_trip_shape(self, trip_id, line_name, origin, destination):
        """
        智能获取形状：先查本地缓存，没有再去 API 下载
        Key = "线路名_起点_终点" (例如: ICE 702_Munich_Berlin)
        """
        # 生成唯一指纹 (指纹不包含 trip_id，因为 trip_id 每天都变，但路不变)
        cache_key = f"{line_name}_{origin}_{destination}"

        # 1. 查本地缓存 (极速)
        if cache_key in self.shapes_cache:
            return self.shapes_cache[cache_key]

        # 2. 本地没有，去 API 下载 (慢)
        try:
            # 限制请求频率
            time.sleep(0.25)
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=3)

            if res.status_code == 200:
                data = res.json()
                encoded = data.get('trip', {}).get('polyline')
                if encoded:
                    points = polyline.decode(encoded)

                    # 存入缓存并保存到文件
                    self.shapes_cache[cache_key] = points
                    self.save_shapes_cache()  # 实时保存，越用越聪明

                    return points
        except:
            pass

        return None

    def get_realtime_departures(self, station_id):
        try:
            # 获取当前站点的名字 (用于缓存 Key)
            origin_name = "Unknown"
            for k, v in self.target_stations.items():
                if v == station_id: origin_name = k; break

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 120, "results": 20, "when": "now"}

            res = requests.get(url, params=params, timeout=5)
            if res.status_code != 200: return 0, []

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

                if not dest_coords: continue

                trip_id = dep.get('tripId')
                line_name = dep.get('line', {}).get('name', '?')
                real_shape = None

                # === 智能形状获取 ===
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