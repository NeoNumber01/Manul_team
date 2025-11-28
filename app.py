import streamlit as st
from streamlit_folium import st_folium
import folium
from data.api_client import TransportAPI
from core.traffic_system import TrafficSystem

st.set_page_config(layout="wide", page_title="DB Impact Monitor")


# === 0. 核心：颜色渐变算法 ===
def get_traffic_color(delay_min):
    """
    根据延误时间返回 hex 颜色
    """
    if delay_min < 1:
        return "#00cc66"  # 🟢 准点 (绿色)
    elif delay_min < 4:
        return "#aadd22"  # 🟡 轻微 (黄绿)
    elif delay_min < 10:
        return "#ffcc00"  # 🟠 拥堵 (黄色)
    elif delay_min < 20:
        return "#ff6600"  # 🔴 严重 (橙红)
    elif delay_min < 60:
        return "#cc0000"  # 🛑 极其严重 (深红)
    else:
        return "#9900cc"  # 🟣 瘫痪 (紫色)


# === 1. 数据加载 ===
@st.cache_resource
def load_data():
    api = TransportAPI()
    system = TrafficSystem()
    snapshot = {}

    # 提示用户耐心等待形状下载
    progress_bar = st.progress(0, text="正在同步路网并计算真实轨迹 (需下载大量数据)...")

    total = len(api.target_stations)
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


try:
    data = load_data()
except Exception as e:
    st.error(f"数据加载异常: {e}")
    data = {}

if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# === 3. 界面 ===
st.title("🚆 UrbanPulse: 实时故障传导分析")

col1, col2 = st.columns([1, 3])

# --- 左侧：列表 ---
with col1:
    st.subheader("📋 核心枢纽状态")

    for name, info in data.items():
        delay = info['avg_delay']
        # 使用我们的新颜色函数来给左侧文字也上色
        color_hex = get_traffic_color(delay)

        # Streamlit 的 markdown 支持颜色
        label = f"{name} (+{delay:.0f}min)"

        is_expanded = (st.session_state.selected_station == name)

        with st.expander(label, expanded=is_expanded):
            # 显示带颜色的指标
            st.markdown(f"#### 状态颜色: <span style='color:{color_hex}'>■■■■■</span>", unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            c1.metric("Rank", f"{info['rank']:.4f}")
            c2.metric("Impact", f"{info['impact']:.1f}")

            if st.button(f"📍 定位 {name}", key=f"btn_{name}"):
                st.session_state.selected_station = name
                st.rerun()

            st.markdown("---")
            for train in info['details']:
                if not train['dest_coords']: continue

                d_time = train['delay']
                # 每一行文字也根据延误变色
                line_color = get_traffic_color(d_time)
                shape_icon = "〰️" if train.get('real_shape') else "📏"

                html_text = f"<span style='color:{line_color}'><b>{train['line']}</b> → {train['to']} (+{d_time:.0f}) {shape_icon}</span>"
                st.markdown(html_text, unsafe_allow_html=True)

# --- 右侧：地图 ---
with col2:
    map_center = [51.1657, 10.4515]
    zoom = 6

    if st.session_state.selected_station:
        sel_info = data.get(st.session_state.selected_station)
        if sel_info:
            map_center = sel_info['pos']
            zoom = 8

    m = folium.Map(
        location=map_center,
        zoom_start=zoom,
        tiles="CartoDB dark_matter",
        min_zoom=6,
        max_bounds=True,
        min_lat=47.0, max_lat=55.5,
        min_lon=5.5, max_lon=15.5
    )

    # A. 绘制所有站点
    for name, info in data.items():
        if not info['pos']: continue

        is_selected = (name == st.session_state.selected_station)

        # 颜色逻辑升级
        circle_color = get_traffic_color(info['avg_delay'])

        radius = 12 if is_selected else 5
        opacity = 1.0 if is_selected else 0.8

        folium.CircleMarker(
            location=info['pos'],
            radius=radius,
            color=circle_color,  # 边框颜色
            fill=True,
            fill_color=circle_color,  # 填充颜色
            fill_opacity=opacity,
            weight=2,
            tooltip=f"{name} (+{info['avg_delay']:.0f}min)",
            popup=None
        ).add_to(m)

    # B. 绘制连线
    # 1. 背景线 (为了不乱，背景线还是保持暗淡，不参与彩色)
    for name, info in data.items():
        if name == st.session_state.selected_station: continue
        start = info['pos']
        for train in info['details']:
            end = train['dest_coords']
            if not end: continue
            real_shape = train.get('real_shape')

            style = {'color': '#333333', 'weight': 1, 'opacity': 0.3}
            if real_shape:
                folium.PolyLine(locations=real_shape, **style).add_to(m)
            else:
                folium.PolyLine(locations=[start, end], **style).add_to(m)

    # 2. 高亮线 (使用渐变色！)
    if st.session_state.selected_station:
        node = st.session_state.selected_station
        info = data.get(node)
        if info:
            start = info['pos']
            for train in info['details']:
                end = train['dest_coords']
                if not end: continue

                real_shape = train.get('real_shape')

                # === 核心：使用渐变色 ===
                line_color = get_traffic_color(train['delay'])

                if real_shape:
                    folium.PolyLine(
                        locations=real_shape,
                        color=line_color,
                        weight=4,
                        opacity=0.9,
                        tooltip=f"{train['line']} (+{train['delay']:.0f}min)"
                    ).add_to(m)
                else:
                    # 如果是直线，用虚线区分
                    folium.PolyLine(
                        locations=[start, end],
                        color=line_color,
                        weight=2,
                        opacity=0.8,
                        dash_array='5, 10',
                        tooltip=f"{train['line']} (直线预估)"
                    ).add_to(m)

    output = st_folium(m, width=900, height=700, key="main_map")

    if output['last_object_clicked']:
        clicked = output['last_object_clicked']
        if 'tooltip' in clicked:
            # tooltip 现在包含 "+5min" 等字样，需要清洗提取名字
            raw_text = clicked['tooltip']
            # 比如 "Heilbronn Hbf (+5min)" -> 取第一个括号前的内容
            name = raw_text.split(" (")[0]

            if name in data and st.session_state.selected_station != name:
                st.session_state.selected_station = name
                st.rerun()