import streamlit as st
from streamlit_folium import st_folium
import folium
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem

st.set_page_config(layout="wide", page_title="DB Impact Monitor")


# === 1. 数据加载 (含真实路径下载) ===
@st.cache_resource
def load_data():
    api = TransportAPI()
    system = TrafficSystem()
    snapshot = {}

    # 进度条 (下载形状会慢一点点，给用户反馈)
    progress_bar = st.progress(0, text="正在同步全德路网及真实轨迹...")

    total = len(api.target_stations)
    # 按名字排序，让列表更好看
    sorted_stations = sorted(api.target_stations.items())

    for idx, (name, sid) in enumerate(sorted_stations):
        coords = api.get_coords(name)
        if not coords: continue

        avg_delay, details = api.get_realtime_departures(sid)
        rank = system.get_rank(name)
        impact = avg_delay * rank * 1000

        snapshot[name] = {
            "pos": coords,
            "avg_delay": avg_delay,
            "details": details,
            "rank": rank,
            "impact": impact
        }
        progress_bar.progress((idx + 1) / total)

    progress_bar.empty()
    return snapshot


# 加载数据
try:
    data = load_data()
except Exception as e:
    st.error(f"数据加载异常: {e}")
    data = {}

# === 2. 状态管理 ===
if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# === 3. 界面布局 ===
st.title("🚆 UrbanPulse: 实时故障传导分析")

col1, col2 = st.columns([1, 2.5])

# --- 左侧：全网站点列表 (恢复你要的功能) ---
with col1:
    st.subheader("📋 全网实时监控")
    st.caption("点击列表可直接定位，或点击地图查看")

    if not data:
        st.warning("暂无数据")

    # 遍历所有站点，生成列表
    for name, info in data.items():
        delay = info['avg_delay']
        # 状态灯
        status_icon = "🔴" if delay > 5 else "🟢"

        # 标题显示：站名 + 延误时长
        label = f"{status_icon} {name} (+{delay:.0f}min)"

        # 如果是当前选中的站点，默认展开
        is_expanded = (st.session_state.selected_station == name)

        with st.expander(label, expanded=is_expanded):
            # 1. 核心指标
            c1, c2 = st.columns(2)
            c1.metric("PageRank", f"{info['rank']:.4f}")
            c2.metric("Impact", f"{info['impact']:.1f}")

            # 2. 定位按钮
            if st.button(f"📍 定位 {name}", key=f"btn_{name}"):
                st.session_state.selected_station = name
                st.rerun()

            st.markdown("---")
            st.caption("🚦 实时发车详情 (含轨迹状态):")

            # 3. 详细文字列表
            visible_lines = 0
            for train in info['details']:
                d_time = train['delay']
                line_icon = "🔴" if d_time > 5 else "🟢"

                # 图标：〰️=真实弯道, 📏=直线, ❌=无法画图
                shape_icon = "〰️" if train.get('real_shape') else ("📏" if train['dest_coords'] else "❌")

                if train['dest_coords']: visible_lines += 1

                st.write(f"{line_icon} {shape_icon} **{train['line']}** → {train['to']} (+{d_time:.0f})")

            if visible_lines == 0:
                st.caption("⚠️ 暂无地理数据")

# --- 右侧：地图 (含真实铁路网底图) ---
with col2:
    map_center = [50.5, 10.0]
    zoom = 6

    # 选中时自动聚焦
    if st.session_state.selected_station:
        sel_node = st.session_state.selected_station
        if sel_node in data and data[sel_node]['pos']:
            map_center = data[sel_node]['pos']
            zoom = 9

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter")

    # 1. 叠加 OpenRailwayMap (真实铁轨层)
    folium.TileLayer(
        tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        attr='OpenRailwayMap',
        name="Railways",
        overlay=True,
        opacity=0.5
    ).add_to(m)

    # 2. 画站点圆点
    for name, info in data.items():
        if not info['pos']: continue
        color = "#ff4b4b" if info['avg_delay'] > 5 else "#00c0f2"

        # 选中变大
        radius = 10 if name == st.session_state.selected_station else 6
        opacity = 1.0 if name == st.session_state.selected_station else 0.8

        folium.CircleMarker(
            location=info['pos'],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=opacity,
            tooltip=f"{name}",
            popup=None
        ).add_to(m)

    # 3. 画连线 (混合模式：真实弯道 + 直线)
    if st.session_state.selected_station:
        node = st.session_state.selected_station
        info = data.get(node)

        if info and info['pos']:
            start = info['pos']

            for train in info['details']:
                end = train['dest_coords']
                real_shape = train.get('real_shape')

                is_delayed = train['delay'] > 5
                line_color = "#ff4b4b" if is_delayed else "#00c0f2"

                # 情况 A: 有真实轨迹 -> 画实线
                if real_shape:
                    folium.PolyLine(
                        locations=real_shape,
                        color=line_color,
                        weight=4,
                        opacity=0.9,
                        tooltip=f"REAL: {train['line']} -> {train['to']}"
                    ).add_to(m)

                # 情况 B: 只有终点坐标 -> 画虚线
                elif end:
                    folium.PolyLine(
                        locations=[start, end],
                        color=line_color,  # 颜色淡一点
                        weight=2,
                        opacity=0.6,
                        dash_array='5, 10',  # 虚线表示"逻辑连接"
                        tooltip=f"LOGICAL: {train['line']} -> {train['to']}"
                    ).add_to(m)

    # 4. 渲染与点击
    output = st_folium(m, width=900, height=700, key="main_map")

    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            name = clicked['tooltip']
            if name in data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()