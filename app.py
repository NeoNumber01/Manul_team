import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd

# 核心模块
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem
from viz import create_3d_map

st.set_page_config(layout="wide", page_title="DB UrbanPulse")


# === 0. 辅助: 颜色 ===
def get_traffic_color(delay_min):
    if delay_min < 1:
        return "#00cc66"
    elif delay_min < 5:
        return "#aadd22"
    elif delay_min < 15:
        return "#ffcc00"
    elif delay_min < 30:
        return "#ff6600"
    elif delay_min < 60:
        return "#cc0000"
    else:
        return "#9900cc"


def get_traffic_color_rgb(delay_min):
    if delay_min < 1:
        return [0, 204, 102]
    elif delay_min < 5:
        return [170, 221, 34]
    elif delay_min < 15:
        return [255, 204, 0]
    elif delay_min < 30:
        return [255, 102, 0]
    elif delay_min < 60:
        return [204, 0, 0]
    else:
        return [153, 0, 204]


# === 1. 数据加载 (纯 API，极速版) ===
@st.cache_data(ttl=120, show_spinner=False)  # 缓存 2 分钟
def fetch_live_data():
    api = TransportAPI()
    system = TrafficSystem()
    snapshot = {}

    # 这里的进度条会比之前快很多
    progress_bar = st.progress(0, text="正在并发同步实时数据...")

    stations = sorted(api.target_stations.items())
    total = len(stations)

    for idx, (name, sid) in enumerate(stations):
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


try:
    with st.spinner("正在连接 DB 实时路网..."):
        data = fetch_live_data()
except Exception as e:
    st.error(f"数据同步失败: {e}")
    data = {}

if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# === 2. 侧边栏 ===
with st.sidebar:
    st.title("🚆 UrbanPulse")

    if st.button("🔄 强制刷新"):
        fetch_live_data.clear()
        st.rerun()

    mode = st.radio("视图模式", ["🗺️ 2D 实时监控", "🌐 3D 全网透视", "📊 数据洞察"])

    st.divider()

    if mode != "📊 数据洞察":
        st.subheader("📍 核心枢纽")
        # 快速定位下拉框
        options = ["- 全局视图 -"] + list(data.keys())
        # 找出当前选中的 index
        curr_idx = 0
        if st.session_state.selected_station in options:
            curr_idx = options.index(st.session_state.selected_station)

        selected = st.selectbox("选择站点", options, index=curr_idx)

        if selected != "- 全局视图 -" and selected != st.session_state.selected_station:
            st.session_state.selected_station = selected
            st.rerun()

        if st.session_state.selected_station:
            node = st.session_state.selected_station
            info = data.get(node)
            if info:
                st.metric("当前延误", f"{info['avg_delay']:.1f} min")
                st.caption("发车列表:")
                for train in info['details']:
                    if not train['dest_coords']: continue
                    icon = "🔴" if train['delay'] > 5 else "🟢"
                    st.write(f"{icon} **{train['line']}** → {train['to']}")

# === 3. 主视图 ===

if mode == "🗺️ 2D 实时监控":
    st.header("实时路网监控 (2D)")

    map_center = [51.1657, 10.4515]
    zoom = 6
    if st.session_state.selected_station:
        sel_info = data.get(st.session_state.selected_station)
        if sel_info:
            map_center = sel_info['pos']
            zoom = 8

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter", min_zoom=6)

    # === 关键优化：使用 OpenRailwayMap 在线图层作为背景 ===
    # 不加载本地文件，速度极快，但依然能看到所有铁轨细节
    folium.TileLayer(
        tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        attr='OpenRailwayMap',
        name="Railways",
        overlay=True,
        opacity=0.4  # 调低透明度，让它成为背景，不抢红绿线的风头
    ).add_to(m)

    # A. 动态点
    for name, info in data.items():
        if not info['pos']: continue
        is_selected = (name == st.session_state.selected_station)
        color = get_traffic_color(info['avg_delay'])
        radius = 12 if is_selected else 6

        folium.CircleMarker(
            location=info['pos'], radius=radius, color=color, fill=True, fill_color=color,
            fill_opacity=1.0 if is_selected else 0.8, tooltip=f"{name} (+{info['avg_delay']:.0f}min)", popup=None
        ).add_to(m)

    # B. 动态线
    if st.session_state.selected_station:
        node = st.session_state.selected_station
        info = data.get(node)
        if info:
            start = info['pos']
            for train in info['details']:
                end = train['dest_coords']
                if not end: continue
                real_shape = train.get('real_shape')
                line_color = get_traffic_color(train['delay'])

                # 有真实形状画实线，没形状画虚线
                if real_shape:
                    folium.PolyLine(locations=real_shape, color=line_color, weight=4, opacity=0.9,
                                    tooltip=train['line']).add_to(m)
                else:
                    folium.PolyLine(locations=[start, end], color=line_color, weight=2, opacity=0.7,
                                    dash_array='5,10').add_to(m)

    output = st_folium(m, width=1200, height=750, key="folium_map")

    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            name = clicked['tooltip'].split(" (")[0]
            if name in data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()

elif mode == "🌐 3D 全网透视":
    st.header("全网 3D 透视")
    deck = create_3d_map(data, st.session_state.selected_station)
    st.pydeck_chart(deck)

elif mode == "📊 数据洞察":
    st.header("网络韧性分析报告")
    table_data = []
    for name, info in data.items():
        table_data.append({
            "Station": name,
            "PageRank": info['rank'],
            "Delay (min)": info['avg_delay'],
            "Impact Score": info['impact']
        })
    df = pd.DataFrame(table_data).sort_values(by="Impact Score", ascending=False)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("💥 关键节点排行")
        st.dataframe(df.style.background_gradient(subset=['Impact Score'], cmap='Reds'), use_container_width=True)
    with c2:
        st.subheader("📉 延误分布")
        st.bar_chart(df.set_index("Station")['Delay (min)'])