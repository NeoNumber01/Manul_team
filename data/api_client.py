import requests
import time
import json
import os
import polyline  # <--- 新增这个库


class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"
        self.station_lookup = {}
        self.load_station_database()

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
            "Köln Hbf": "8000207"
        }

    def load_station_database(self):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, 'stations_db.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                self.station_lookup = json.load(f)
        except:
            self.station_lookup = {"Heilbronn Hbf": (49.1427, 9.2109)}

    def get_coords(self, name):
        if not name: return None
        if name in self.station_lookup: return self.station_lookup[name]
        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")
        for k, v in self.station_lookup.items():
            if clean_name in k: return v
        return None

    # === 新增：获取真实的弯曲路径 ===
    def fetch_trip_shape(self, trip_id):
        """
        根据 Trip ID 向 API 请求真实的铁轨形状
        """
        try:
            # 这里必须加一点延迟，否则并发请求真实形状极其容易触发限流
            time.sleep(0.2)

            # polyline=true 是关键！
            url = f"{self.base_url}/trips/{trip_id}?polyline=true"
            res = requests.get(url, timeout=3)

            if res.status_code == 200:
                data = res.json()
                trip = data.get('trip', {})
                # API 返回的是 Google Polyline 编码字符串，需要解码
                encoded_line = trip.get('polyline')
                if encoded_line:
                    # 解码为 [(lat, lon), (lat, lon), ...]
                    return polyline.decode(encoded_line)
            return None
        except:
            return None

    def get_realtime_departures(self, station_id):
        """
        获取车次，并顺便获取前几趟车的真实形状
        """
        try:
            time.sleep(0.2)
            url = f"{self.base_url}/stops/{station_id}/departures"
            params = {"duration": 120, "results": 15, "when": "now"}

            res = requests.get(url, params=params, timeout=5)
            if res.status_code != 200: return 0, []

            data = res.json()
            departures = data.get('departures', [])

            details = []
            delays = []

            # 限制只获取前 3 趟车的真实形状，防止启动太慢！
            shape_limit = 3

            for i, dep in enumerate(departures):
                delay = dep.get('delay', 0) or 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)

                # 获取 Trip ID 用于查询形状
                trip_id = dep.get('tripId')
                real_shape = None

                # 只有前几趟车，且有终点坐标的，我们才去查形状
                if i < shape_limit and trip_id and dest_coords:
                    # print(f"   Trying to fetch shape for {dep.get('line', {}).get('name')}...")
                    real_shape = self.fetch_trip_shape(trip_id)

                details.append({
                    "line": dep.get('line', {}).get('name', '?'),
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords,
                    "real_shape": real_shape  # 这里存着真实的弯曲路径！
                })

            avg = sum(delays) / len(delays) if delays else 0
            return avg, details
        except Exception as e:
            print(f"API Error: {e}")
            return 0, []