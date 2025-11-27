import networkx as nx


class TrafficSystem:
    def __init__(self):
        # 1. 定义路网拓扑 (定义谁是枢纽)
        # 即使地图上只画了几个点，这个图结构决定了 PageRank 的科学性
        self.connections = [
            ("Frankfurt Hbf", "Mannheim Hbf"),
            ("Frankfurt Hbf", "Köln Hbf"),
            ("Frankfurt Hbf", "Würzburg Hbf"),
            ("Frankfurt Hbf", "Berlin Hbf"),
            ("Mannheim Hbf", "Stuttgart Hbf"),
            ("Stuttgart Hbf", "Munich Hbf"),
            ("Stuttgart Hbf", "Heilbronn Hbf"),  # 我们的主场连接
            ("Munich Hbf", "Nürnberg Hbf"),
            ("Nürnberg Hbf", "Leipzig Hbf"),
            ("Leipzig Hbf", "Berlin Hbf"),
            ("Berlin Hbf", "Hamburg Hbf"),
            ("Hamburg Hbf", "Köln Hbf"),
            ("Karlsruhe Hbf", "Mannheim Hbf"),
            ("Karlsruhe Hbf", "Stuttgart Hbf"),
            ("Hannover Hbf", "Berlin Hbf"),
            ("Hannover Hbf", "Frankfurt Hbf")
        ]

        # 2. 初始化图
        self.G = nx.DiGraph()
        self.G.add_edges_from(self.connections)

        # 3. 计算 PageRank
        try:
            self.pagerank_scores = nx.pagerank(self.G, alpha=0.85)
        except:
            # 防止没装 scipy 报错
            self.pagerank_scores = nx.pagerank(self.G, alpha=0.85, tol=1e-4)

    def get_rank(self, station_name):
        """获取权重，带模糊匹配"""
        if station_name in self.pagerank_scores:
            return self.pagerank_scores[station_name]

        for name, score in self.pagerank_scores.items():
            if name in station_name or station_name in name:
                return score
        return 0.015  # 默认低权重