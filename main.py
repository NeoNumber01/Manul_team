# 这里的 import 会去 ui 文件夹里找 MapGenerator
from data.api_client import TransportAPI
from core.graph_builder import GraphEngine
from core.impact_calculator import ImpactAnalyzer
from ui.map_visualizer import MapGenerator


def main():
    print("🚀 启动 UrbanPulse 系统...")

    # 1. 初始化模块
    api = TransportAPI()
    graph_engine = GraphEngine()
    map_gen = MapGenerator()

    impact_results = {}

    # 2. 构建图 (Nodes)
    print("📡 正在获取站点数据...")
    for name, sid in api.known_stations.items():
        # 获取坐标
        lat, lon = api.get_station_location(sid)
        if lat:
            graph_engine.add_station_node(name, sid, lat, lon)

    # 3. 建立连接 (模拟拓扑结构)
    print("🕸️ 正在构建网络拓扑...")
    graph_engine.add_connection("Heilbronn Hbf", "Stuttgart Hbf")
    graph_engine.add_connection("Stuttgart Hbf", "Munich Hbf")
    graph_engine.add_connection("Stuttgart Hbf", "Frankfurt Hbf")
    graph_engine.add_connection("Frankfurt Hbf", "Berlin Hbf")
    graph_engine.add_connection("Berlin Hbf", "Hamburg Hbf")
    graph_engine.add_connection("Munich Hbf", "Berlin Hbf")  # 增加一条长途线

    # 4. 计算 PageRank
    print("🧮 正在运行 PageRank 算法...")
    pageranks = graph_engine.calculate_pagerank()

    # 5. 获取实时数据并计算影响
    print("⚡ 正在获取实时延误数据 (为了防止被封，每个请求会停顿 0.6秒)...")
    for name, sid in api.known_stations.items():
        avg_delay, _ = api.get_realtime_departures(sid)
        rank = pageranks.get(name, 0)

        # 核心：计算 Impact
        score = ImpactAnalyzer.calculate_score(rank, avg_delay)
        impact_results[name] = score

        print(f"  [{name}] 延误: {avg_delay:.1f}min | 权重: {rank:.3f} | 影响指数: {score:.1f}")

        # ... (前面的代码保持不变)

        # 6. 生成可视化
        print("🎨 生成 Dashboard...")
        map_gen.generate(graph_engine.G, pageranks, impact_results, "dashboard.html")

        # 👇 新增这几行代码 👇
        import webbrowser
        import os

        # 获取文件的绝对路径，确保浏览器能找到
        file_path = os.path.abspath("dashboard.html")
        print(f"正在浏览器中打开: {file_path}")
        webbrowser.open('file://' + file_path)

    if __name__ == "__main__":
        main()