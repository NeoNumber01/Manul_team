import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
import time

# Core Modules
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem
from viz import create_3d_map

st.set_page_config(layout="wide", page_title="DB UrbanPulse")


# ==========================
# 0. Helper: Colors
# ==========================
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


# ==========================
# 1. Static Resource Loading
# ==========================
@st.cache_resource
def load_static_resources():
    """
    Load heavy static assets (API client, Algorithm system).
    """
    api = TransportAPI()
    system = TrafficSystem()
    return api, system


try:
    with st.spinner("Initializing Map Engine & Coordinate DB..."):
        api, system = load_static_resources()
except Exception as e:
    st.error(f"Failed to load static resources: {e}")
    st.stop()


# ==========================
# 2. Dynamic Data Loading
# ==========================
# 关键修改：ttl=3600 (1小时)。这意味着演示期间它绝不会自动刷新卡顿！
# 只有当你点击"Refresh Data"按钮时，它才会更新。
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_realtime_data():
    snapshot = {}
    stations = sorted(api.target_stations.items())

    # 使用 st.status 代替 progress bar，体验更流畅
    with st.status("Fetching Real-time Data...", expanded=True) as status:
        total = len(stations)
        for idx, (name, sid) in enumerate(stations):
            # 给用户一点文字反馈，让他知道没死机
            status.write(f"Syncing {name}...")

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
        status.update(label="Data Sync Complete!", state="complete", expanded=False)

    return snapshot


try:
    data = fetch_realtime_data()
except Exception as e:
    st.error(f"Real-time sync failed: {e}")
    data = {}

if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# ==========================
# 3. Sidebar Navigation
# ==========================
with st.sidebar:
    st.title("🚆 UrbanPulse")
    st.markdown("### Railway Resilience Analysis")

    # 刷新按钮：只有点击这里，才会触发加载
    if st.button("🔄 Refresh Data Now"):
        fetch_realtime_data.clear()
        st.rerun()

    mode = st.radio("View Mode", ["🗺️ 2D Monitor", "🌐 3D Perspective", "📊 Data Insights"], index=0)

    st.divider()

    if mode != "📊 Data Insights":
        st.subheader("📍 Quick Locate")
        station_names = list(data.keys())
        selected = st.selectbox("Select Station", ["- Global View -"] + station_names)

        if selected != "- Global View -" and selected != st.session_state.selected_station:
            st.session_state.selected_station = selected
            st.rerun()

        if st.session_state.selected_station:
            node = st.session_state.selected_station
            info = data.get(node)
            if info:
                st.metric("Current Delay", f"{info['avg_delay']:.1f} min")
                st.metric("Impact Index", f"{info['impact']:.1f}")
                st.caption("Departing Trains:")

                for train in info['details']:
                    if not train['dest_coords']: continue

                    delay_val = train['delay']
                    icon = "🔴" if delay_val > 5 else "🟢"
                    st.write(f"{icon} **{train['line']}** → {train['to']} (+{delay_val:.0f} min)")

# ==========================
# 4. Main View Logic
# ==========================

if mode == "🗺️ 2D Monitor":
    st.header("Real-time Network Monitor (2D)")

    map_center = [51.1657, 10.4515]
    zoom = 6
    if st.session_state.selected_station:
        sel_info = data.get(st.session_state.selected_station)
        if sel_info:
            map_center = sel_info['pos']
            zoom = 8

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter", min_zoom=6)

    # A. Static Background (OpenRailwayMap Online Layer)
    folium.TileLayer(
        tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        attr='OpenRailwayMap',
        name="Rail Network",
        overlay=True,
        opacity=0.4
    ).add_to(m)

    # B. Dynamic Points
    for name, info in data.items():
        if not info['pos']: continue
        is_selected = (name == st.session_state.selected_station)
        color = get_traffic_color(info['avg_delay'])
        radius = 12 if is_selected else 5

        folium.CircleMarker(
            location=info['pos'], radius=radius, color=color, fill=True, fill_color=color,
            fill_opacity=1.0 if is_selected else 0.8, tooltip=f"{name} (+{info['avg_delay']:.0f}min)", popup=None
        ).add_to(m)

    # C. Dynamic Lines
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

                tooltip_text = f"{train['line']} -> {train['to']} (+{train['delay']:.0f} min)"

                if real_shape:
                    folium.PolyLine(locations=real_shape, color=line_color, weight=4, opacity=0.9,
                                    tooltip=tooltip_text).add_to(m)
                else:
                    folium.PolyLine(locations=[start, end], color=line_color, weight=2, opacity=0.8, dash_array='5,10',
                                    tooltip=tooltip_text).add_to(m)

    output = st_folium(m, width=1400, height=800, key="folium_map")

    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            name = clicked['tooltip'].split(" (")[0]
            if name in data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()

elif mode == "🌐 3D Perspective":
    st.header("3D Network Perspective")
    st.caption("Visualizing long-distance connections and delay propagation using ArcLayer")
    deck = create_3d_map(data, st.session_state.selected_station)
    st.pydeck_chart(deck)

elif mode == "📊 Data Insights":
    st.header("Network Resilience Report")
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
        st.subheader("💥 Critical Nodes Ranking")
        st.dataframe(df.style.background_gradient(subset=['Impact Score'], cmap='Reds'), use_container_width=True)
    with c2:
        st.subheader("📉 Delay Distribution")
        st.bar_chart(df.set_index("Station")['Delay (min)'])