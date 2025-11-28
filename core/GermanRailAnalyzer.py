import streamlit as st
import folium
from streamlit_folium import st_folium
import networkx as nx
import requests
import json
import os
import pandas as pd
import numpy as np
from folium.plugins import TimestampedGeoJson
from math import radians, cos, sin, asin, sqrt
from datetime import datetime, timedelta
import random


# ==========================================
# 1. 数据加载层 (Data Layer)
# ==========================================
class RailDataLoader:
    """
    负责数据的获取与缓存。解决"每次请求都慢"的问题。
    它会优先读取本地 JSON，不存在时才去 OpenStreetMap 下载。
    """

    def __init__(self, filename="german_railway_network.json"):
        self.filename = filename

    def load_or_fetch_data(self):
        if os.path.exists(self.filename):
            st.success(f"✅ 从本地加载数据: {self.filename}")
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            st.warning(
                "⚠️ 本地未找到数据，正在从 OpenStreetMap (Overpass API) 下载德国主要路网... 这可能需要 1-2 分钟，请耐心等待。")
            return self._fetch_from_overpass()

    def _fetch_from_overpass(self):
        """
        使用 Overpass API 获取德国主要铁路干线 (usage=main)。
        这样既能拿到真实数据，又不会因为包含所有支线而导致文件过大。
        """
        # Overpass QL 查询语句
        # 范围大致覆盖德国 (47.2, 5.8, 55.1, 15.1)
        query = """
        [out:json][timeout:180];
        (
          way["railway"="rail"]["usage"="main"](47.2,5.8,55.1,15.1);
        );
        out geom;
        """
        url = "[http://overpass-api.de/api/interpreter](http://overpass-api.de/api/interpreter)"

        try:
            response = requests.get(url, params={'data': query})
            response.raise_for_status()
            data = response.json()

            # 将 Overpass 的 JSON 转换为标准的 GeoJSON 格式以便后续处理
            geojson = self._convert_overpass_to_geojson(data)

            # 保存到本地，下次直接用
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(geojson, f)

            st.success(f"✅ 数据下载并保存成功: {self.filename}")
            return geojson
        except Exception as e:
            st.error(f"❌ 数据下载失败: {e}")
            return None

    def _convert_overpass_to_geojson(self, overpass_data):
        """将 OSM 原始数据转换为 GeoJSON FeatureCollection"""
        features =
        for element in overpass_data.get('elements', ):
            if element['type'] == 'way' and 'geometry' in element:
                # 提取坐标点
                coords = [[pt['lon'], pt['lat']] for pt in element['geometry']]

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": element.get('tags', {})
                }
                features.append(feature)
        return {"type": "FeatureCollection", "features": features}


# ==========================================
# 2. 图分析引擎 (Graph Engine)
# ==========================================
class RailGraph:
    """
    负责构建图网络、处理延误数据以及计算 PageRank。
    """

    def __init__(self):
        self.G = nx.DiGraph()
        self.pagerank_scores = {}

    def build_from_geojson(self, geojson_data):
        """
        解析 GeoJSON LineString 构建 NetworkX 图。
        节点 = 线路的端点（简化处理，用于拓扑分析）
        边 = 铁路线路
        """
        self.G.clear()
        if not geojson_data:
            return

        for feature in geojson_data['features']:
            coords = feature['geometry']['coordinates']
            props = feature['properties']

            # 这里的逻辑是将每一段铁轨视为两个节点（起点和终点）之间的边
            # 在真实复杂路网中，应该做节点合并(Snap)，但演示目的下直接取首尾足矣
            if len(coords) < 2: continue

            u = tuple(coords)  # 起点坐标 (lon, lat)
            v = tuple(coords[-1])  # 终点坐标 (lon, lat)

            # 计算物理距离 (简单欧氏距离近似，或者用 Haversine)
            dist = self._haversine(u[1], u, v[1], v)

            # 添加边。weight 初始为 1.0
            # path 属性存储完整的几何路径，用于动画绘制
            self.G.add_edge(u, v, weight=1.0, distance=dist, path=coords, props=props)
            self.G.add_edge(v, u, weight=1.0, distance=dist, path=coords[::-1], props=props)

    def update_delays(self, delay_data_source):
        """
        更新图的权重。
        你可以在这里接入你现有的 API 数据。
        """
        # 假设 delay_data_source 是你 API 返回的数据
        # 这里为了演示，我们使用随机模拟，或者根据你 hackathon 的主题：
        # "影响更重的线路颜色更深" -> 这意味着我们需要提高延误线路的权重

        # 模拟：随机选择一些节点作为延误源
        nodes = list(self.G.nodes())
        if not nodes: return

        # 模拟：假设这些区域发生延误
        affected_nodes = random.sample(nodes, min(len(nodes), 20))

        for u, v, data in self.G.edges(data=True):
            # 基础权重
            weight = 1.0

            # 如果边的端点在受影响列表中，增加权重
            # 在 PageRank 中，指向高权重节点的边会提升该节点的重要性
            if u in affected_nodes or v in affected_nodes:
                weight = 10.0  # 假设延误严重

            data['weight'] = weight
            # 存储延误信息供前端显示
            data['delay_status'] = "High Delay" if weight > 1 else "On Time"

    def calculate_pagerank(self):
        """
        计算 PageRank。
        """
        if len(self.G) == 0: return
        try:
            # 使用 weight='weight'，这样延误越大的线路，其连接的枢纽 PageRank 越高
            self.pagerank_scores = nx.pagerank(self.G, weight='weight', alpha=0.85)

            # 归一化分数 (0-1) 以便绘图
            max_val = max(self.pagerank_scores.values())
            min_val = min(self.pagerank_scores.values())
            for k in self.pagerank_scores:
                self.pagerank_scores[k] = (self.pagerank_scores[k] - min_val) / (max_val - min_val + 1e-9)

        except Exception as e:
            st.error(f"PageRank 计算错误: {e}")

    def _haversine(self, lat1, lon1, lat2, lon2):
        """计算两点间距离 (km)"""
        R = 6371
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return R * c


# ==========================================
# 3. 可视化层 (Visualization Layer)
# ==========================================
class MapVisualizer:
    def __init__(self, graph_manager):
        self.graph_mgr = graph_manager

    def get_color_by_pagerank(self, u, v):
        """
        根据边的两个端点的 PageRank 平均值来决定线路颜色。
        PageRank 越高 -> 颜色越深/越红。
        """
        pr_u = self.graph_mgr.pagerank_scores.get(u, 0)
        pr_v = self.graph_mgr.pagerank_scores.get(v, 0)
        avg_pr = (pr_u + pr_v) / 2

        # 颜色映射逻辑
        if avg_pr > 0.7: return '#8B0000', 4  # 深红 (严重影响)
        if avg_pr > 0.4: return '#FF4500', 3  # 橙红 (中等)
        if avg_pr > 0.2: return '#FFD700', 2  # 金色 (轻微)
        return '#228B22', 1  # 绿色 (正常)

    def generate_animation_geojson(self):
        """
        生成由 TimestampedGeoJson 使用的数据。
        让火车沿着 LineString 的真实路径移动。
        """
        features =
        current_time = datetime.now()

        # 随机选取一部分线路生成火车
        edges = list(self.graph_mgr.G.edges(data=True))
        selected_edges = random.sample(edges, min(len(edges), 50))  # 演示用，选50条线

        for u, v, data in selected_edges:
            path_coords = data.get('path', )
            if len(path_coords) < 2: continue

            # 确定这条线路的颜色（基于 PageRank）
            color, _ = self.get_color_by_pagerank(u, v)

            # 模拟：每列车跑完全程需要的时间 (秒)
            duration_sec = 20
            steps = len(path_coords)

            # 为路径上的每个点分配时间戳
            for i in range(steps):
                coord = path_coords[i]

                # 计算当前点的时间偏移
                time_offset = (i / steps) * duration_sec
                timestamp = (current_time + timedelta(seconds=time_offset)).isoformat()

                # 构建 GeoJSON Feature
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': coord
                    },
                    'properties': {
                        'time': timestamp,
                        'style': {'color': color},
                        'icon': 'circle',
                        'iconstyle': {
                            'fillColor': color,
                            'fillOpacity': 1,
                            'stroke': 'false',
                            'radius': 5
                        },
                        'popup': f"Train on line"
                    }
                }
                features.append(feature)

        return features

    def create_map(self):
        # 初始化地图，中心定在德国
        m = folium.Map(location=[51.1657, 10.4515], zoom_start=6, tiles='CartoDB dark_matter')

        # 1. 绘制静态线路图 (背景)
        # 颜色根据 PageRank 动态变化
        for u, v, data in self.graph_mgr.G.edges(data=True):
            color, weight = self.get_color_by_pagerank(u, v)
            coords = data.get('path', )
            # Folium 需要 (lat, lon)，GeoJSON 是 (lon, lat)，注意反转
            folium_coords = [[p[1], p] for p in coords]

            folium.PolyLine(
                folium_coords,
                color=color,
                weight=weight,
                opacity=0.6,
                tooltip=f"Status: {data.get('delay_status')}"
            ).add_to(m)

        # 2. 生成动画数据并添加图层
        anim_data = self.generate_animation_geojson()
        if anim_data:
            TimestampedGeoJson(
                {'type': 'FeatureCollection', 'features': anim_data},
                period='PT1S',
                duration='PT1S',
                transition_time=200,
                auto_play=True,
                loop=True,
                max_speed=1,
                loop_button=True,
                date_options='HH:mm:ss',
                time_slider_drag_update=True
            ).add_to(m)

        return m


# ==========================================
# 4. 主程序 (Main Interface)
# ==========================================
def main():
    st.set_page_config(layout="wide", page_title="DB Delay Visualizer")

    st.title("🚂 德国铁路延误影响可视化 (PageRank + Animation)")
    st.markdown("""
    该项目将铁路网络视为有向图，利用 **PageRank** 算法计算延误在网络中的“权重”。
    *   **颜色越深 (红)**：表示该路段在当前的延误网络中权重越高（受影响越大）。
    *   **本地缓存优化**：首次运行会下载数据，之后直接读取 `german_railway_network.json`。
    """)

    # 侧边栏
    with st.sidebar:
        st.header("控制面板")
        run_analysis = st.button("运行分析 & 生成地图")

    if run_analysis:
        # 1. 加载数据
        loader = RailDataLoader()
        geojson = loader.load_or_fetch_data()

        if geojson:
            # 2. 构建图 & 注入延误
            graph = RailGraph()
            with st.spinner("正在构建路网拓扑..."):
                graph.build_from_geojson(geojson)

            with st.spinner("正在注入实时延误数据 (API Simulation)..."):
                # 这里调用你的 API 数据接口
                graph.update_delays(None)

            with st.spinner("正在运行 PageRank 算法..."):
                graph.calculate_pagerank()

            # 3. 渲染地图
            viz = MapVisualizer(graph)
            m = viz.create_map()

            st.success("可视化生成完毕！")
            st_folium(m, width="100%", height=700)

            # 显示 PageRank Top 榜单
            st.subheader("🚨 当前延误影响最大的关键节点 (Top Critical Nodes)")
            # 简单的表格展示
            sorted_nodes = sorted(graph.pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:10]
            df = pd.DataFrame(sorted_nodes, columns=)
            st.table(df)


if __name__ == "__main__":
    main()