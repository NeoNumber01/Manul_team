import streamlit as st
from streamlit_folium import st_folium
import folium

# 👇 引用刚才拆分出去的核心模块
from core.traffic_system import TrafficSystem

st.set_page_config(layout="wide", page_title="PageRank Traffic Impact")


# === 1. 初始化系统 ===
@st.cache_resource
def load_system():
    return TrafficSystem()


system = load_system()

# === 2. 状态管理 ===
if "selected_node" not in st.session_state:
    st.session_state.selected_node = None

# === 3. 侧边栏 UI ===
with st.sidebar:
    st.title("🛡️ 交通韧性分析")
    st.caption("基于 PageRank 算法的故障影响评估")

    if st.session_state.selected_node:
        node = st.session_state.selected_node
        status = system.get_station_status(node)

        st.divider()
        st.header(node)

        # 核心指标
        st.metric("PageRank (节点重要性)", f"{status['rank']:.4f}")

        # 智能变色逻辑
        if status['impact'] > 150:
            color, msg = "inverse", "⚠️ 严重网络冲击"
        elif status['impact'] > 50:
            color, msg = "normal", "⚡ 中等影响"
        else:
            color, msg = "off", "✅ 低影响"

        st.metric("实时延误", f"{status['delay']:.1f} min")
        st.metric("Impact Index", f"{status['impact']:.1f}", delta=msg, delta_color=color)

        st.write("---")
        if node == "Frankfurt Hbf":
            st.warning("法兰克福是高权重枢纽，延误将导致全网瘫痪。")
        elif node == "Heilbronn Hbf":
            st.info("海尔布隆权重较低，延误影响仅限于局部。")
    else:
        st.info("👈 请点击地图上的站点查看分析")

# === 4. 地图 UI ===
st.subheader("🇩🇪 德国铁路关键节点拓扑图")

m = folium.Map(location=[50.5, 10.0], zoom_start=6, tiles="CartoDB dark_matter")

# A. 绘制节点
for name, coords in system.stations.items():
    status = system.get_station_status(name)

    # 颜色与半径逻辑
    if status['impact'] > 150:
        color = "#ff4b4b"  # 红
    elif status['impact'] > 50:
        color = "#ffa500"  # 橙
    else:
        color = "#00c0f2"  # 蓝

    radius = status['rank'] * 1000

    folium.CircleMarker(
        location=coords,
        radius=max(5, radius),
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        tooltip=f"{name} (Rank: {status['rank']:.3f})",
        popup=None  # 禁用默认弹窗，确保点击事件能传回 Streamlit
    ).add_to(m)

# B. 绘制连线 (仅选中时)
if st.session_state.selected_node:
    node = st.session_state.selected_node
    status = system.get_station_status(node)

    for line in status['lines']:
        line_color = "#ff4b4b" if status['delay'] > 10 else "#00c0f2"
        folium.PolyLine(
            locations=line['coords'],
            color=line_color,
            weight=3,
            opacity=0.8,
            tooltip=f"{node} -> {line['to']}"
        ).add_to(m)

# === 5. 交互逻辑 ===
output = st_folium(m, width=1000, height=600, key="main_map")

if output['last_object_clicked']:
    clicked = output['last_object_clicked']
    if 'tooltip' in clicked:
        # 解析名字: "Frankfurt Hbf (Rank: ...)" -> "Frankfurt Hbf"
        station_name = clicked['tooltip'].split(" (")[0]

        if station_name in system.stations:
            if st.session_state.selected_node != station_name:
                st.session_state.selected_node = station_name
                st.rerun()