import streamlit as st
from streamlit_folium import st_folium
import folium
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem

st.set_page_config(layout="wide", page_title="DB Impact Monitor")


# === 1. 数据加载 (智能收集所有点) ===
@st.cache_resource
def load_data():
    api = TransportAPI()
    system = TrafficSystem()

    # 1. 主动节点 (Active): 我们专门查询的大站
    active_data = {}
    # 2. 被动节点 (Passive): 线路终点提到的小站
    passive_nodes = {}

    progress_bar = st.progress(0, text="正在构建全网拓扑...")

    # --- 第一阶段：获取核心数据 ---
    sorted_stations = sorted(api.target_stations.items())
    total = len(sorted_stations)

    for idx, (name, sid) in enumerate(sorted_stations):
        coords = api.get_coords(name)
        if not coords: continue

        # 获取实时数据
        avg_delay, details = api.get_realtime_departures(sid)
        rank = system.get_rank(name)
        impact = avg_delay * rank * 1000

        active_data[name] = {
            "pos": coords,
            "avg_delay": avg_delay,
            "details": details,
            "rank": rank,
            "impact": impact,
            "type": "main"  # 标记为主节点
        }

        # --- 第二阶段：收集所有终点 (填补虚空) ---
        for train in details:
            dest_name = train['to']
            dest_coords = train['dest_coords']

            # 如果这个终点有坐标，且不是主节点，就把它加入被动节点库
            if dest_coords and dest_name not in active_data and dest_name not in passive_nodes:
                # 被动节点没有延误数据，但我们需要把它画出来
                passive_rank = system.get_rank(dest_name)  # 通常很低
                passive_nodes[dest_name] = {
                    "pos": dest_coords,
                    "rank": passive_rank,
                    "type": "passive"  # 标记为被动节点
                }

        progress_bar.progress((idx + 1) / total)

    progress_bar.empty()
    return active_data, passive_nodes


# 加载数据
try:
    active_data, passive_nodes = load_data()
    # 合并用于地图绘制
    all_map_data = {**active_data, **passive_nodes}
except Exception as e:
    st.error(f"数据加载异常: {e}")
    active_data, passive_nodes, all_map_data = {}, {}, {}

# === 2. 状态管理 ===
if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# === 3. 界面布局 ===
st.title("🚆 UrbanPulse: 实时故障传导分析")

col1, col2 = st.columns([1, 3])

# --- 左侧：只显示有数据的主节点 ---
with col1:
    st.subheader("📋 核心枢纽监控")

    for name, info in active_data.items():
        delay = info['avg_delay']
        status_icon = "🔴" if delay > 5 else "🟢"
        label = f"{status_icon} {name} (+{delay:.0f}min)"

        is_expanded = (st.session_state.selected_station == name)

        with st.expander(label, expanded=is_expanded):
            c1, c2 = st.columns(2)
            c1.metric("Rank", f"{info['rank']:.4f}")
            c2.metric("Impact", f"{info['impact']:.1f}")

            # 按钮
            if st.button(f"📍 定位", key=f"btn_{name}"):
                st.session_state.selected_station = name
                st.rerun()

            st.caption("实时发车:")
            for train in info['details']:
                d_time = train['delay']
                line_icon = "🔴" if d_time > 5 else "🟢"
                st.write(f"{line_icon} **{train['line']}** → {train['to']}")

# --- 右侧：地图 ---
with col2:
    # 智能定中心
    map_center = [50.0, 10.0]
    zoom = 6
    if st.session_state.selected_station:
        sel_info = all_map_data.get(st.session_state.selected_station)
        if sel_info:
            map_center = sel_info['pos']
            zoom = 9  # 选中时自动放大，这样能看清小站！

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter")

    # A. 绘制所有节点 (解决虚空问题)
    for name, info in all_map_data.items():
        # 样式逻辑：区分大站和小站
        if info['type'] == 'main':
            # 大站：大圈，根据延误变色
            radius = 8 + (info['rank'] * 100)  # Rank越高圈越大
            color = "#ff4b4b" if info['avg_delay'] > 5 else "#00c0f2"
            fill_opacity = 1.0
            z_index_offset = 1000  # 保证大站在最上层
        else:
            # 小站 (被动)：极小的灰/白圈
            # 这样缩小看时几乎不可见，放大看时就是连接点
            radius = 3
            color = "#888888"
            fill_opacity = 0.5
            z_index_offset = 0

        folium.CircleMarker(
            location=info['pos'],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=fill_opacity,
            weight=1,
            tooltip=f"{name}",  # 鼠标放上去显示名字
            popup=None,
            z_index_offset=z_index_offset
        ).add_to(m)

    # B. 绘制连线
    if st.session_state.selected_station:
        node = st.session_state.selected_station
        # 只从主节点库里找连线数据
        if node in active_data:
            info = active_data[node]
            start = info['pos']

            for train in info['details']:
                end = train['dest_coords']
                if end:
                    is_delayed = train['delay'] > 5
                    line_color = "#ff4b4b" if is_delayed else "#00c0f2"
                    weight = 3 if is_delayed else 1.5
                    opacity = 0.9 if is_delayed else 0.6

                    folium.PolyLine(
                        locations=[start, end],
                        color=line_color,
                        weight=weight,
                        opacity=opacity,
                        tooltip=f"{train['line']} -> {train['to']}"
                    ).add_to(m)

    output = st_folium(m, width=900, height=700, key="main_map")

    # 点击逻辑：允许点击小站，但如果点击小站，可能只是居中，不展开侧边栏
    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            name = clicked['tooltip']
            # 只有点击主节点才触发侧边栏联动
            if name in active_data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()
            # 如果点击了小站，仅打印提示（可选）
            elif name in passive_nodes:
                st.toast(f"📍 小站点: {name} (无实时发车数据)", icon="ℹ️")