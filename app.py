import streamlit as st
from streamlit_folium import st_folium
import folium
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem

st.set_page_config(layout="wide", page_title="DB Impact Monitor")


# === 1. 数据加载 ===
@st.cache_resource
def load_data():
    api = TransportAPI()
    system = TrafficSystem()
    snapshot = {}

    # 进度条
    progress_bar = st.progress(0, text="正在同步全德路网实时数据...")

    idx = 0
    total = len(api.target_stations)
    # 按名字排序，方便在列表里找
    sorted_stations = sorted(api.target_stations.items())

    for name, sid in sorted_stations:
        lat, lon = api.get_coords(name)
        avg_delay, details = api.get_realtime_departures(sid)
        rank = system.get_rank(name)
        impact = avg_delay * rank * 1000

        snapshot[name] = {
            "pos": (lat, lon),
            "avg_delay": avg_delay,
            "details": details,
            "rank": rank,
            "impact": impact
        }
        idx += 1
        progress_bar.progress(idx / total)

    progress_bar.empty()
    return snapshot


data = load_data()

# === 2. 状态管理 ===
if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# === 3. 界面布局 ===
st.title("🚆 UrbanPulse: 实时故障传导分析")

# 使用 1:3 的比例，左边放长列表，右边放地图
col1, col2 = st.columns([1, 2.5])

# --- 左侧：所有站点的详细列表 (回归经典功能) ---
with col1:
    st.subheader("📋 全网站点监控")
    st.caption("点击展开查看各线路详情")

    # 遍历所有数据，生成折叠面板
    for name, info in data.items():
        # 1. 准备标题状态
        delay = info['avg_delay']
        impact = info['impact']

        # 图标逻辑：延误严重显示红灯，否则绿灯
        status_icon = "🔴" if delay > 5 else "🟢"

        # 标题显示：站名 + 平均延误 + Impact
        label = f"{status_icon} {name} (+{delay:.0f}min)"

        # 2. 生成折叠面板 (Expander)
        # 如果当前选中的是这个站，默认展开 (expanded=True)
        is_expanded = (st.session_state.selected_station == name)

        with st.expander(label, expanded=is_expanded):
            # 显示核心指标
            c1, c2 = st.columns(2)
            c1.metric("PageRank", f"{info['rank']:.4f}")
            c2.metric("Impact", f"{info['impact']:.1f}")

            st.markdown("---")
            st.markdown("**🚦 实时发车详情:**")

            # 3. 列出该站的所有线路 (这里就是你要的文字信息！)
            visible_lines = 0
            for train in info['details']:
                d_time = train['delay']
                # 单条线路的红绿灯
                line_icon = "🔴" if d_time > 5 else "🟢"
                # 是否能画图
                map_icon = "🗺️" if train['dest_coords'] else ""
                if train['dest_coords']: visible_lines += 1

                # 打印每一行文字：线路 -> 终点 (延误)
                st.write(f"{line_icon} **{train['line']}** → {train['to']} (+{d_time:.0f}) {map_icon}")

            if visible_lines == 0:
                st.caption("⚠️ 无坐标数据，无法画线")

            # 4. 增加一个按钮，点击可以聚焦到地图
            # key 必须唯一，所以加上 name
            if st.button(f"📍 在地图上定位 {name}", key=f"btn_{name}"):
                st.session_state.selected_station = name
                st.rerun()

# --- 右侧：地图 ---
with col2:
    # 默认中心
    map_center = [50.5, 10.0]
    zoom = 6

    # 如果选中了站点，地图中心自动飞过去
    if st.session_state.selected_station:
        sel_node = st.session_state.selected_station
        if sel_node in data and data[sel_node]['pos']:
            map_center = data[sel_node]['pos']
            zoom = 8  # 稍微放大一点

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter")

    # A. 画城市点
    for name, info in data.items():
        if not info['pos']: continue
        color = "#ff4b4b" if info['avg_delay'] > 5 else "#00c0f2"

        # 稍微突出显示选中的点
        radius = 10 if name == st.session_state.selected_station else 6
        opacity = 1.0 if name == st.session_state.selected_station else 0.8

        folium.CircleMarker(
            location=info['pos'],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=opacity,
            tooltip=f"{name} (点击查看)",
            popup=None
        ).add_to(m)

    # B. 画连线 (仅针对选中)
    if st.session_state.selected_station:
        node = st.session_state.selected_station
        info = data.get(node)

        if info and info['pos']:
            start = info['pos']
            for train in info['details']:
                end = train['dest_coords']
                if end:
                    is_delayed = train['delay'] > 5
                    line_color = "#ff4b4b" if is_delayed else "#00c0f2"
                    weight = 4 if is_delayed else 2
                    opacity = 0.9 if is_delayed else 0.5

                    folium.PolyLine(
                        locations=[start, end],
                        color=line_color,
                        weight=weight,
                        opacity=opacity,
                        tooltip=f"{train['line']} -> {train['to']}"
                    ).add_to(m)

    # C. 渲染
    output = st_folium(m, width=800, height=700, key="main_map")

    # D. 点击逻辑
    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            name = clicked['tooltip'].split(" (")[0]
            if name in data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()