import networkx as nx
import random


class TrafficSystem:
    def __init__(self):
        # 1. 真实的站点坐标 (Data)
        self.stations = {
            "Frankfurt Hbf": (50.1071, 8.6638),
            "Munich Hbf": (48.1403, 11.5588),
            "Berlin Hbf": (52.5256, 13.3696),
            "Hamburg Hbf": (53.5528, 10.0067),
            "Stuttgart Hbf": (48.7832, 9.1818),
            "Heilbronn Hbf": (49.1427, 9.2109),  # 我们的主场
            "Köln Hbf": (50.9432, 6.9586),
            "Mannheim Hbf": (49.4793, 8.4699),
            "Nürnberg Hbf": (49.4456, 11.0829),
            "Leipzig Hbf": (51.3465, 12.3833)
        }

        # 2. 真实的路网连接 (Topology)
        self.connections = [
            ("Frankfurt Hbf", "Mannheim Hbf"),
            ("Frankfurt Hbf", "Köln Hbf"),
            ("Frankfurt Hbf", "Würzburg Hbf"),
            ("Frankfurt Hbf", "Berlin Hbf"),
            ("Mannheim Hbf", "Stuttgart Hbf"),
            ("Stuttgart Hbf", "Munich Hbf"),
            ("Stuttgart Hbf", "Heilbronn Hbf"),
            ("Munich Hbf", "Nürnberg Hbf"),
            ("Nürnberg Hbf", "Leipzig Hbf"),
            ("Leipzig Hbf", "Berlin Hbf"),
            ("Berlin Hbf", "Hamburg Hbf"),
            ("Hamburg Hbf", "Köln Hbf")
        ]

        # 3. 初始化图 (Graph)
        self.G = nx.DiGraph()
        self.G.add_nodes_from(self.stations.keys())
        self.G.add_edges_from(self.connections)

        # 4. 运行 PageRank 算法 (Algorithm)
        try:
            # 尝试使用 scipy 加速
            self.pagerank_scores = nx.pagerank(self.G, alpha=0.85)
        except ImportError:
            # 如果 scipy 还没装好，回退到普通 python 计算，防止报错
            print("⚠️ Scipy not found, using python implementation")
            self.pagerank_scores = nx.pagerank(self.G, alpha=0.85, tol=1e-4)

    def get_station_status(self, station_name):
        """
        获取某个站点的状态 (Model Logic)
        """
        # A. 模拟延误 (Scenario)
        if station_name == "Heilbronn Hbf":
            avg_delay = 15  # 延误 15 分钟
        elif station_name == "Frankfurt Hbf":
            avg_delay = 15  # 同样延误 15 分钟
        else:
            avg_delay = random.uniform(0, 5) if random.random() > 0.3 else 0

        # B. 计算 Impact (Math)
        rank = self.pagerank_scores.get(station_name, 0.01)
        impact_score = avg_delay * rank * 1000

        # C. 准备连线数据
        neighbors = list(self.G.successors(station_name)) if station_name in self.G else []
        lines = []
        for neighbor in neighbors:
            if neighbor in self.stations:
                lines.append({
                    "to": neighbor,
                    "coords": [self.stations[station_name], self.stations[neighbor]],
                    "delay": avg_delay
                })

        return {
            "rank": rank,
            "delay": avg_delay,
            "impact": impact_score,
            "lines": lines
        }