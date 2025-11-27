import networkx as nx


class GraphEngine:
    def __init__(self):
        self.G = nx.DiGraph()  # 有向图

    def add_station_node(self, name, station_id, lat, lon):
        """添加节点"""
        self.G.add_node(name, id=station_id, pos=(lat, lon))

    def add_connection(self, start_name, end_name):
        """添加边 (代表有车次相连)"""
        # 如果边已存在，增加权重 (代表班次更密集)
        if self.G.has_edge(start_name, end_name):
            self.G[start_name][end_name]['weight'] += 1
        else:
            self.G.add_edge(start_name, end_name, weight=1)

    def calculate_pagerank(self):
        """运行 PageRank 算法"""
        # alpha=0.85 是标准阻尼系数
        try:
            return nx.pagerank(self.G, alpha=0.85, weight='weight')
        except:
            # 防止空图报错
            return {}