import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
import time
import os

# Core Modules
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem
from viz import create_3d_map

# === 1. 页面基础配置 ===
st.set_page_config(
    layout="wide",
    page_title="Central Command",
    page_icon="★",
    initial_sidebar_state="expanded"
)


# === 2. 注入苏联风 CSS ===
def inject_custom_css():
    st.markdown("""
        <style>
        /* 1. 字体 */
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

        html, body, [class*="css"] {
            font-family: 'Share Tech Mono', monospace;
            background-color: #121212; /* 深黑背景 */
            color: #E0E0E0;
        }

        /* 2. 顶部 Header */
        .header-container {
            background-color: #8B0000; /* 深红 */
            padding: 1.5rem;
            border: 2px solid #FFD700; /* 金色边框 */
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 5px 5px 0px #000;
        }
        .header-title {
            color: #FFD700;
            font-size: 28px;
            font-weight: 900;
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        .header-subtitle {
            color: #FFC0C0;
            font-size: 14px;
            text-transform: uppercase;
        }

        /* 3. 指标卡片 */
        div[data-testid="stMetric"] {
            background-color: #1E1E1E;
            border: 1px solid #555;
            border-left: 5px solid #FFD700;
            padding: 10px;
            border-radius: 0px !important;
        }
        div[data-testid="stMetric"] label {
            color: #FFD700 !important;
            font-size: 0.8rem;
            text-transform: uppercase;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #FFFFFF !important;
            font-size: 1.5rem;
        }

        /* 4. 侧边栏 */
        section[data-testid="stSidebar"] {
            background-color: #080808;
            border-right: 2px solid #8B0000;
        }

        /* 5. 按钮 */
        button {
            border-radius: 0px !important;
            border: 1px solid #FFD700 !important;
            background-color: #330000 !important;
            color: #FFD700 !important;
            text-transform: uppercase;
            font-weight: bold;
        }
        button:hover {
            background-color: #FFD700 !important;
            color: #000000 !important;
        }

        /* 6. 列表项 */
        .train-list-item {
            padding: 10px;
            margin-bottom: 8px;
            background-color: #1A1A1A;
            border: 1px solid #333;
            border-left: 4px solid #333;
            font-size: 0.9rem;
        }
        .status-critical { border-left-color: #FF0000; color: #FFaaaa; }
        .status-normal { border-left-color: #00FF00; color: #ccffcc; }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)


inject_custom_css()

# === 3. 自定义 Header ===
st.markdown("""
    <div class="header-container">
        <div>
            <div class="header-title">★ CENTRAL RAILWAY COMMAND</div>
            <div class="header-subtitle">State Infrastructure Monitoring Bureau | Section: DE-GRID</div>
        </div>
        <div style="text-align:right; font-family:'Courier New'; font-size: 12px;">
            <span style="color:#FFD700">STATUS:</span> OPERATIONAL<br>
            <span style="color:#FFD700">PROTOCOL:</span> PAGERANK-V2<br>
            <span style="color:#FFD700">DATE:</span> 2025-11-26
        </div>
    </div>
""", unsafe_allow_html=True)


# ==========================
# 0. Helper: Colors
# ==========================
def get_traffic_color(delay_min):
    if delay_min < 1:
        return "#00FF00"
    elif delay_min < 5:
        return "#ADFF2F"
    elif delay_min < 15:
        return "#FFFF00"
    elif delay_min < 30:
        return "#FF4500"
    elif delay_min < 60:
        return "#FF0000"
    else:
        return "#FF00FF"


def get_traffic_color_rgb(delay_min):
    if delay_min < 1:
        return [0, 255, 0]
    elif delay_min < 5:
        return [173, 255, 47]
    elif delay_min < 15:
        return [255, 255, 0]
    elif delay_min < 30:
        return [255, 69, 0]
    elif delay_min < 60:
        return [255, 0, 0]
    else:
        return [255, 0, 255]


# ==========================
# 1. Static Resource Loading
# ==========================
@st.cache_resource
def load_static_resources():
    api = TransportAPI()
    system = TrafficSystem()
    return api, system


try:
    with st.spinner("INITIALIZING MAINFRAME..."):
        api, system = load_static_resources()
except Exception as e:
    st.error(f"SYSTEM FAILURE: {e}")
    st.stop()


# ==========================
# 2. Dynamic Data Loading
# ==========================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_realtime_data():
    snapshot = {}
    stations = sorted(api.target_stations.items())

    with st.status("ESTABLISHING UPLINK...", expanded=True) as status:
        total = len(stations)
        for idx, (name, sid) in enumerate(stations):
            status.write(f"Scanning Sector: {name}...")
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
        status.update(label="DATA SYNCHRONIZED", state="complete", expanded=False)

    return snapshot


try:
    data = fetch_realtime_data()
except Exception as e:
    st.error(f"LINK FAILED: {e}")
    data = {}

if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# ==========================
# 3. Sidebar Navigation (Modified for Cat Image)
# ==========================
with st.sidebar:
    # --- 新增布局：星星 + 猫猫 并排 ---
    c1, c2 = st.columns([1, 2], gap="small")

    with c1:
        # 垂直居中的大红星
        st.markdown(
            "<h1 style='text-align: center; color: #CD0000; font-size: 50px; margin: 0; padding-top: 10px;'>★</h1>",
            unsafe_allow_html=True)

    with c2:
        # 显示你的猫猫图片
        # 确保图片文件名完全一致！
        img_path = "afe0a9295697727f98750710dd47056e.jpg"
        if os.path.exists(img_path):
            st.image(img_path, width=110)
        else:
            st.warning("Cat img not found")

    st.markdown("<h3 style='text-align: center; color: #FFD700; margin-top: -10px;'>OPERATIONS BUREAU</h3>",
                unsafe_allow_html=True)
    st.markdown("---")

    if st.button("🔄 SYNC DATA"):
        fetch_realtime_data.clear()
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    mode = st.radio("VIEW MODE", ["🗺️ TACTICAL MAP (2D)", "🌐 GLOBAL HOLOGRAPH (3D)", "📊 INTEL REPORT"], index=0)

    st.markdown("---")

    if mode != "📊 INTEL REPORT":
        st.markdown("#### 📍 SECTOR SELECTOR")
        station_names = list(data.keys())
        selected = st.selectbox("Select Station", ["- GLOBAL OVERVIEW -"] + station_names, label_visibility="collapsed")

        if selected != "- GLOBAL OVERVIEW -" and selected != st.session_state.selected_station:
            st.session_state.selected_station = selected
            st.rerun()

        if st.session_state.selected_station:
            node = st.session_state.selected_station
            info = data.get(node)
            if info:
                # 选中的卡片样式
                st.markdown(f"""
                <div style="border: 2px solid #FFD700; padding: 10px; background: #330000;">
                    <small style="color:#FFD700;">TARGET SECTOR</small><br>
                    <b style="font-size:1.2em; color:#FFF;">{node.upper()}</b>
                </div>
                """, unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                c1.metric("LATENCY", f"{info['avg_delay']:.1f}m")
                c2.metric("IMPACT", f"{info['impact']:.1f}")

                st.markdown("#### TRAFFIC LOG")
                for train in info['details']:
                    if not train['dest_coords']: continue

                    delay_val = train['delay']
                    css_class = "status-critical" if delay_val > 5 else "status-normal"
                    time_str = f"+{delay_val:.0f}m" if delay_val > 0 else "NOMINAL"

                    st.markdown(f"""
                    <div class="train-list-item {css_class}">
                        <b>{train['line']}</b> » {train['to']} <span style="float:right;">{time_str}</span>
                    </div>
                    """, unsafe_allow_html=True)

# ==========================
# 4. Main View Logic
# ==========================

if mode == "🗺️ TACTICAL MAP (2D)":
    # 2D 视图逻辑

    map_center = [51.1657, 10.4515]
    zoom = 6
    if st.session_state.selected_station:
        sel_info = data.get(st.session_state.selected_station)
        if sel_info:
            map_center = sel_info['pos']
            zoom = 8

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter", min_zoom=6)

    folium.TileLayer(
        tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        attr='OpenRailwayMap',
        name="Rail Network",
        overlay=True,
        opacity=0.3
    ).add_to(m)

    for name, info in data.items():
        if not info['pos']: continue
        is_selected = (name == st.session_state.selected_station)
        color = get_traffic_color(info['avg_delay'])
        radius = 12 if is_selected else 5

        folium.CircleMarker(
            location=info['pos'], radius=radius, color=color, fill=True, fill_color=color,
            fill_opacity=1.0 if is_selected else 0.8, tooltip=f"{name} (+{info['avg_delay']:.0f}m)", popup=None
        ).add_to(m)

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
                tooltip_text = f"{train['line']} >> {train['to']}"

                if real_shape:
                    folium.PolyLine(locations=real_shape, color=line_color, weight=3, opacity=0.9,
                                    tooltip=tooltip_text).add_to(m)
                else:
                    folium.PolyLine(locations=[start, end], color=line_color, weight=2, opacity=0.7, dash_array='5,10',
                                    tooltip=tooltip_text).add_to(m)

    st_folium(m, width=1400, height=800, key="folium_map")

elif mode == "🌐 GLOBAL HOLOGRAPH (3D)":
    deck = create_3d_map(data, st.session_state.selected_station)
    st.pydeck_chart(deck)

elif mode == "📊 INTEL REPORT":
    st.markdown("### 📊 NETWORK RESILIENCE INTELLIGENCE")

    table_data = []
    for name, info in data.items():
        table_data.append({
            "SECTOR": name,
            "IMPORTANCE (PageRank)": info['rank'],
            "LATENCY (min)": info['avg_delay'],
            "IMPACT SCORE": info['impact']
        })
    df = pd.DataFrame(table_data).sort_values(by="IMPACT SCORE", ascending=False)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("#### ⚠️ CRITICAL NODES")
        st.dataframe(df.style.background_gradient(subset=['IMPACT SCORE'], cmap='Reds'), use_container_width=True)
    with c2:
        st.markdown("#### 📉 LATENCY DISTRIBUTION")
        st.bar_chart(df.set_index("SECTOR")['LATENCY (min)'], color="#CD0000")