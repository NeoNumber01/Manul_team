import random
import time


class TransportAPI:
    def __init__(self):
        # 1. 内置坐标库 (这是地图能显示的关键)
        self.station_data = {
            "Heilbronn Hbf": {"id": "8000156", "pos": (49.1427, 9.2109)},
            "Stuttgart Hbf": {"id": "8000096", "pos": (48.7832, 9.1818)},
            "Munich Hbf": {"id": "8000261", "pos": (48.1403, 11.5588)},
            "Frankfurt Hbf": {"id": "8000105", "pos": (50.1071, 8.6638)},
            "Berlin Hbf": {"id": "8011160", "pos": (52.5256, 13.3696)},
            "Hamburg Hbf": {"id": "8002549", "pos": (53.5528, 10.0067)},
            "Köln Hbf": {"id": "8000207", "pos": (50.9432, 6.9586)},
            "Mannheim Hbf": {"id": "8000244", "pos": (49.4793, 8.4699)},
            "Karlsruhe Hbf": {"id": "8000191", "pos": (48.9935, 8.4021)},
            "Würzburg Hbf": {"id": "8000152", "pos": (49.8018, 9.9358)},
            "Nürnberg Hbf": {"id": "8000284", "pos": (49.4456, 11.0829)},
            "Ulm Hbf": {"id": "8000170", "pos": (48.3994, 9.9829)},
            "Leipzig Hbf": {"id": "8010205", "pos": (51.3465, 12.3833)},
            "Dresden Hbf": {"id": "8010085", "pos": (51.0405, 13.7314)},
            "Hannover Hbf": {"id": "8000152", "pos": (52.3766, 9.7410)}
        }
        self.known_stations = {k: v["id"] for k, v in self.station_data.items()}
        self.all_cities = list(self.station_data.keys())

    def get_station_location(self, station_id):
        # 只要 ID 对，绝对返回坐标
        for name, data in self.station_data.items():
            if data["id"] == station_id:
                return data["pos"]
        return None, None

    def find_coordinates_by_name(self, city_name):
        if city_name in self.station_data:
            return self.station_data[city_name]["pos"]
        # 模糊匹配
        for key, data in self.station_data.items():
            if city_name in key:
                return data["pos"]
        return None

    def get_realtime_departures(self, station_id):
        # 模拟数据生成：0.01秒返回，绝不超时
        detailed_info = []
        delays = []

        # 找到当前站名
        current_name = "Unknown"
        for k, v in self.station_data.items():
            if v["id"] == station_id:
                current_name = k
                break

        # 生成 5 趟随机车次
        for i in range(5):
            # 随机选一个终点（不能是自己）
            targets = [x for x in self.all_cities if x != current_name]
            target = random.choice(targets)

            # 特殊剧本：海尔布隆 -> 斯图加特 必延误 (为了演示效果)
            if current_name == "Heilbronn Hbf" and target == "Stuttgart Hbf":
                delay = random.uniform(15, 30)
                line = "RE 10"
            else:
                delay = random.uniform(0, 5) if random.random() > 0.3 else 0
                line = f"ICE {random.randint(100, 900)}"

            delays.append(delay)
            detailed_info.append({
                "line": line,
                "to": target,
                "delay": delay
            })

        avg_delay = sum(delays) / len(delays) if delays else 0
        return avg_delay, detailed_info