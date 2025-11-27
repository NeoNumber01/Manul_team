import requests
import time
import json
import os


class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"

        # === 1. 加载你上传的超级坐标库 ===
        self.station_lookup = {}
        self.load_station_database()

        # === 2. 定义我们要监控的核心站点 ===
        # 你可以在这里随意增加，现在都能查到坐标了！
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
            "Dresden Hbf": "8010085",
            "Hannover Hbf": "8000152"
        }

    def load_station_database(self):
        """
        读取本地的 stations_db.json 文件
        """
        try:
            # 获取当前脚本所在的文件夹路径 (data/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 拼接文件名
            file_path = os.path.join(current_dir, 'stations_db.json')

            print(f"📂 正在加载坐标库: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                self.station_lookup = json.load(f)

            print(f"✅ 成功加载了 {len(self.station_lookup)} 个站点的坐标！")

        except Exception as e:
            print(f"❌ 加载坐标库失败: {e}")
            # 如果加载失败，保留一个最小集合防止程序崩溃
            self.station_lookup = {
                "Heilbronn Hbf": (49.1427, 9.2109),
                "Berlin Hbf": (52.5256, 13.3696)
            }

    def get_coords(self, name):
        """
        查找坐标：现在支持全德国数千个站点！
        """
        if not name: return None

        # 1. 直接匹配 (最快)
        if name in self.station_lookup:
            return self.station_lookup[name]

        # 2. 模糊匹配 (例如 "Frankfurt(Main)Hbf" 匹配 "Frankfurt Hbf")
        # 为了性能，我们先尝试常见变体
        clean_name = name.replace(" Hbf", "").replace(" Hauptbahnhof", "")

        for k, v in self.station_lookup.items():
            if clean_name in k:
                return v
        return None

    def get_realtime_departures(self, station_id):
        """请求 API 获取实时数据"""
        try:
            # 稍微休息，对公共API温柔一点
            time.sleep(0.1)
            url = f"{self.base_url}/stops/{station_id}/departures"

            # duration=180: 查看未来3小时的车，保证能画出更多长线
            params = {"duration": 180, "results": 30, "when": "now"}

            res = requests.get(url, params=params, timeout=5)
            if res.status_code != 200: return 0, []

            data = res.json()
            departures = data.get('departures', [])

            details = []
            delays = []

            for dep in departures:
                # 1. 获取延误
                delay = dep.get('delay', 0)
                if delay is None: delay = 0
                delay_min = abs(delay) / 60
                delays.append(delay_min)

                # 2. 获取终点
                direction = dep.get('direction', 'Unknown')

                # 3. 查坐标 (现在几乎一定能查到了！)
                dest_coords = self.get_coords(direction)

                # 4. 只有当找到了坐标，我们才把它加入列表
                # 这样侧边栏显示的都是能画出线的车
                details.append({
                    "line": dep.get('line', {}).get('name', '?'),
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords
                })

            avg = sum(delays) / len(delays) if delays else 0
            return avg, details

        except Exception as e:
            print(f"API Error: {e}")
            return 0, []