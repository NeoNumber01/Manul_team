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

        self.load_station_database()

        # === 缓存系统 ===
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
        except Exception as e:
            print(f"Cache save failed: {e}")

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

    def _fetch_single_shape(self, trip_id):
        """线程池调用的单个下载函数"""
        try:
            # 这里的 sleep 对于并发来说是每个线程独立的
            # 如果并发5个，相当于同时在等，效率高5倍
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

    def get_realtime_departures(self, station_id):
        """
        [终极版] 并发下载 + 本地缓存
        """
        try:
            # 获取当前站名用于生成 Cache Key
            origin_name = "Unknown"
            for k, v in self.target_stations.items():
                if v == station_id: origin_name = k; break

            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 120, "results": 15, "when": "now"}

            res = requests.get(url, params=params, timeout=5)
            if res.status_code != 200: return 0, []

            data = res.json()
            departures = data.get('departures', [])

            details = []
            delays = []

            # 1. 预处理：找出哪些需要去网上下，哪些可以直接读缓存
            tasks = []  # (index, trip_id, cache_key)

            # 临时列表，保持顺序
            temp_results = [None] * len(departures)

            for i, dep in enumerate(departures):
                delay = dep.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)

                # 如果没终点，直接跳过画线
                if not dest_coords: continue

                trip_id = dep.get('tripId')
                line_name = dep.get('line', {}).get('name', '?')

                # 构造缓存 Key
                cache_key = f"{line_name}_{origin_name}_{direction}"

                real_shape = None

                # A. 查缓存 (极速)
                if cache_key in self.shapes_cache:
                    real_shape = self.shapes_cache[cache_key]
                # B. 没缓存 -> 加入待下载队列
                elif trip_id:
                    tasks.append((i, trip_id, cache_key))

                # 先存入基本信息
                temp_results[i] = {
                    "line": line_name,
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape  # 如果缓存有，这里就有值；否则是 None
                }

            # 2. 并发下载缺失的形状 (如果有的话)
            if tasks:
                # print(f"🚀 {origin_name}: 正在并发下载 {len(tasks)} 条新线路形状...")
                with ThreadPoolExecutor(max_workers=5) as executor:
                    # 提交所有任务
                    future_to_info = {
                        executor.submit(self._fetch_single_shape, t[1]): t
                        for t in tasks
                    }

                    for future in as_completed(future_to_info):
                        idx, trip_id, cache_key = future_to_info[future]
                        shape = future.result()

                        if shape:
                            # 填回结果列表
                            if temp_results[idx]:
                                temp_results[idx]['real_shape'] = shape
                            # 更新内存缓存
                            self.shapes_cache[cache_key] = shape

                # 3. 下载完一批后，保存到硬盘 (增量更新)
                self.save_shapes_cache()

            # 4. 清理 None 并返回
            details = [x for x in temp_results if x is not None]

            avg = sum(delays) / len(delays) if delays else 0
            return avg, details

        except Exception as e:
            print(f"API Error: {e}")
            return 0, []