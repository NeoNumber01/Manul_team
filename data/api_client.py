import requests
import time


class TransportAPI:
    def __init__(self):
        self.base_url = "https://v6.db.transport.rest"

        # === 核心：坐标库 (画线必须要有终点坐标) ===
        # 这里包含了大城市和海尔布隆周边的区域站点
        self.station_lookup = {
            # --- 核心枢纽 ---
            "Heilbronn Hbf": (49.1427, 9.2109),
            "Stuttgart Hbf": (48.7832, 9.1818),
            "Munich Hbf": (48.1403, 11.5588), "München Hbf": (48.1403, 11.5588),
            "Frankfurt(Main)Hbf": (50.1071, 8.6638), "Frankfurt Hbf": (50.1071, 8.6638),
            "Berlin Hbf": (52.5256, 13.3696),
            "Hamburg Hbf": (53.5528, 10.0067),
            "Köln Hbf": (50.9432, 6.9586),
            "Mannheim Hbf": (49.4793, 8.4699),
            "Karlsruhe Hbf": (48.9935, 8.4021),
            "Würzburg Hbf": (49.8018, 9.9358),
            "Nürnberg Hbf": (49.4456, 11.0829),
            "Ulm Hbf": (48.3994, 9.9829),
            "Leipzig Hbf": (51.3465, 12.3833),
            "Hannover Hbf": (52.3766, 9.7410),
            "Heidelberg Hbf": (49.4036, 8.6757),
            "Düsseldorf Hbf": (51.2199, 6.7943),

            # --- 海尔布隆周边 (保证点击主场时有线看) ---
            "Neckarsulm": (49.1917, 9.2272),
            "Bad Friedrichshall Hbf": (49.2319, 9.2144),
            "Möckmühl": (49.3236, 9.3592),
            "Osterburken": (49.4283, 9.4261),
            "Eppingen": (49.1378, 8.9067),
            "Öhringen Hbf": (49.2003, 9.5017), "Öhringen": (49.2003, 9.5017),
            "Bietigheim-Bissingen": (48.9483, 9.1172),
            "Ludwigsburg": (48.8911, 9.1856),
            "Mosbach-Neckarelz": (49.3444, 9.1239),
            "Sinsheim(Elsenz) Hbf": (49.2536, 8.8728),

            # --- 常见国际/长途终点 ---
            "Basel Bad Bf": (47.5664, 7.6069),
            "Zürich HB": (47.3782, 8.5402),
            "Paris Est": (48.8768, 2.3591),
            "Kassel-Wilhelmshöhe": (51.3137, 9.4475)
        }

        # 我们要监控的主要站点 (API 请求的目标)
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

    def get_coords(self, name):
        """查找坐标，支持模糊匹配"""
        if not name: return None
        if name in self.station_lookup: return self.station_lookup[name]
        for k, v in self.station_lookup.items():
            if name in k or k in name: return v
        return None

    def get_realtime_departures(self, station_id):
        """请求 API 获取实时数据"""
        try:
            time.sleep(0.1)  # 稍微休息防止并发太快
            url = f"{self.base_url}/stops/{station_id}/departures"
            # duration=120 抓取未来2小时的车，增加画出长线的概率
            params = {"duration": 120, "results": 20, "when": "now"}

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

                # 2. 获取终点坐标 (画线关键)
                direction = dep.get('direction', 'Unknown')
                dest_coords = self.get_coords(direction)

                details.append({
                    "line": dep.get('line', {}).get('name', '?'),
                    "to": direction,
                    "delay": delay_min,
                    "dest_coords": dest_coords
                })

            avg = sum(delays) / len(delays) if delays else 0
            return avg, details
        except:
            return 0, []