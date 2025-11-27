import folium
# 必须引入 ImpactAnalyzer 才能在下面使用它
from core.impact_calculator import ImpactAnalyzer


class MapGenerator:
    def generate(self, graph, pagerank_data, impact_data, output_file="dashboard.html"):
        # 以德国为中心初始化
        m = folium.Map(location=[51.1657, 10.4515], zoom_start=6, tiles="CartoDB dark_matter")

        # 绘制站点 (Nodes)
        for node in graph.nodes(data=True):
            name = node[0]
            # 获取坐标
            pos = node[1].get('pos')
            if not pos or pos[0] is None:
                continue

            lat, lon = pos
            rank = pagerank_data.get(name, 0.01)
            impact = impact_data.get(name, 0)

            # 圆圈大小 = PageRank (静态重要性)
            radius = rank * 500

            # 颜色 = Impact (实时影响)
            color = ImpactAnalyzer.get_color(impact)

            popup_text = f"""
            <div style="width: 150px">
                <b>{name}</b><br>
                PageRank: {rank:.4f}<br>
                Impact Score: {impact:.1f}
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=max(5, radius),  # 最小半径5
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=popup_text
            ).add_to(m)

        m.save(output_file)
        print(f"地图已生成: {output_file}")