import os
import time

import pandas as pd
import altair as alt
import streamlit as st
from streamlit_folium import st_folium
import folium
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(*_args, **_kwargs):
        return None

from src.realtime.api_client import TransportAPI
from src.realtime.traffic_system import TrafficSystem
from src.realtime.urban_viz import create_3d_map

st.set_page_config(
    layout="wide",
    page_title="RailBoard",
    page_icon="★",
    initial_sidebar_state="expanded",
)


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        html, body, [class*="css"] {
            font-family: 'Share Tech Mono', monospace;
            background-color: #121212;
            color: #FFFFFF;
        }
        .header-container {
            background-color: #8B0000;
            padding: 1.2rem;
            border: 2px solid #FFD700;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 4px 4px 0px #000;
        }
        .header-title {
            color: #FFFFFF;
            font-size: 24px;
            font-weight: 900;
            letter-spacing: 1.5px;
            text-transform: uppercase;
        }
        .header-subtitle {
            color: #FFFFFF;
            font-size: 12px;
            text-transform: uppercase;
        }
        section[data-testid="stSidebar"] {
            background-color: #080808;
            border-right: 2px solid #8B0000;
        }
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
        /* Bright white text across sidebar controls */
        section[data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        div[role="radiogroup"] label, label {
            color: #FFFFFF !important;
        }
        .stSelectbox label {
            color: #FFFFFF !important;
        }
        /* Selectbox value text: black inside the white box */
        .stSelectbox [data-baseweb="select"] * {
            color: #000000 !important;
        }
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
        /* Force first nav entry label to RailBoard */
        div[data-testid="stSidebarNav"] li:first-of-type a {
            position: relative;
        }
        div[data-testid="stSidebarNav"] li:first-of-type a span {
            visibility: hidden;
        }
        div[data-testid="stSidebarNav"] li:first-of-type a span::after {
            content: "RailBoard";
            visibility: visible;
            position: absolute;
            left: 0;
            top: 0;
        }
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()

st.markdown(
    """
    <div class="header-container">
        <div>
            <div class="header-title">RAILBOARD</div>
            <div class="header-subtitle">State Infrastructure Monitoring Bureau | Section: DE-GRID</div>
        </div>
        <div style="text-align:right; font-family:'Courier New'; font-size: 12px; color:#FFFFFF;">
            <span style="color:#FFD700">STATUS:</span> OPERATIONAL<br>
            <span style="color:#FFD700">PROTOCOL:</span> PAGERANK-V2<br>
            <span style="color:#FFD700">DATE:</span> 2025-11-26
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def get_traffic_color(delay_min: float) -> str:
    """Return a hex color based on delay minutes."""
    if delay_min < 1:
        return "#00cc66"
    if delay_min < 5:
        return "#aadd22"
    if delay_min < 15:
        return "#ffcc00"
    if delay_min < 30:
        return "#ff6600"
    if delay_min < 60:
        return "#cc0000"
    return "#9900cc"


def get_traffic_color_rgb(delay_min: float) -> list[int]:
    """RGB helper for future extensions."""
    if delay_min < 1:
        return [0, 204, 102]
    if delay_min < 5:
        return [170, 221, 34]
    if delay_min < 15:
        return [255, 204, 0]
    if delay_min < 30:
        return [255, 102, 0]
    if delay_min < 60:
        return [204, 0, 0]
    return [153, 0, 204]


@st.cache_resource
def load_static_resources():
    """Load heavy static assets (API client, PageRank system)."""
    api = TransportAPI()
    system = TrafficSystem()
    return api, system


@st.cache_data(
    ttl=3600,
    show_spinner=False,
    hash_funcs={TransportAPI: lambda _x: "api", TrafficSystem: lambda _x: "system"},
)
def fetch_realtime_data(api: TransportAPI, system: TrafficSystem) -> dict:
    """Fetch live departures with status feedback; cached for 1 hour unless manually refreshed."""
    snapshot = {}
    stations = sorted(api.target_stations.items())

    with st.status("ESTABLISHING UPLINK...", expanded=True) as status:
        for name, sid in stations:
            status.write(f"Scanning Sector: {name}...")

            coords = api.get_coords(name)
            if not coords:
                continue

            avg_delay, details = api.get_realtime_departures(sid)
            incoming_avg, incoming = api.get_realtime_arrivals(sid)
            rank = system.get_rank(name)
            impact = avg_delay * rank * 1000

            snapshot[name] = {
                "pos": coords,
                "avg_delay": avg_delay,
                "details": details,  # alias for outgoing (map rendering depends on this key)
                "outgoing": details,
                "incoming": incoming,
                "incoming_avg_delay": incoming_avg,
                "rank": rank,
                "impact": impact,
            }
        status.update(label="DATA SYNCHRONIZED", state="complete", expanded=False)

    return snapshot


def render_sidebar_header(mode: str) -> tuple[bool, str]:
    st.markdown("### OPERATIONS BUREAU", unsafe_allow_html=True)
    st.markdown("---")

    sync_clicked = st.button("🔄 SYNC DATA", key="sync_data")

    st.markdown("<br>", unsafe_allow_html=True)
    choices = ["🗺️ TACTICAL MAP (2D)", "🌐 GLOBAL HOLOGRAPH (3D)", "📊 INTEL REPORT"]
    default_index = choices.index(mode) if mode in choices else 0
    mode_choice = st.radio("VIEW MODE", choices, index=default_index, key="view_mode")

    st.markdown("---")
    return sync_clicked, mode_choice


def render_sidebar_station_section(data: dict, mode: str) -> None:
    if mode == "📊 INTEL REPORT":
        return

    st.markdown("#### 📍 SECTOR SELECTOR")
    station_names = list(data.keys())
    selected = st.selectbox("Select Station", ["- GLOBAL OVERVIEW -"] + station_names, label_visibility="collapsed")
    prev_sel = st.session_state.get("selected_station")
    if selected == "- GLOBAL OVERVIEW -":
        if prev_sel is not None:
            st.session_state["selected_station"] = None
    elif selected != prev_sel:
        st.session_state["selected_station"] = selected

    sel = st.session_state.get("selected_station")
    if sel:
        info = data.get(sel)
        if info:
            st.markdown(
                f"""
                <div style="border: 2px solid #FFD700; padding: 10px; background: #330000;">
                    <small style="color:#FFD700;">TARGET SECTOR</small><br>
                    <b style="font-size:1.2em; color:#FFF;">{sel.upper()}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns(2)
            c1.metric("LATENCY", f"{info['avg_delay']:.1f}m")
            c2.metric("IMPACT", f"{info['impact']:.1f}")

            st.markdown("#### TRAFFIC LOG")
            incoming_trains = info.get("incoming") or []
            outgoing_trains = info.get("outgoing") or info.get("details") or []

            def render_trains(title: str, trains: list[dict], arrow: str, get_label):
                st.markdown(f"**{title}**")
                if not trains:
                    st.caption("No data.")
                    return
                for train in trains:
                    has_coords = train.get("dest_coords") if arrow == "»" else train.get("origin_coords")
                    if not has_coords:
                        continue
                    delay_val = train.get("delay", 0)
                    css_class = "status-critical" if delay_val > 5 else "status-normal"
                    time_str = f"+{delay_val:.0f}m" if delay_val > 0 else "NOMINAL"
                    label = get_label(train)
                    st.markdown(
                        f"""
                        <div class="train-list-item {css_class}">
                            <b>{train['line']}</b> {arrow} {label} <span style="float:right;">{time_str}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            render_trains("Incoming trains", incoming_trains, "«", lambda t: t.get("origin", "Unknown"))
            render_trains("Outgoing trains", outgoing_trains, "»", lambda t: t.get("to", "Unknown"))


def render_map(data: dict) -> None:
    map_center = [51.1657, 10.4515]
    zoom = 6
    selected_station = st.session_state.get("selected_station")
    if selected_station and selected_station in data:
        sel_info = data[selected_station]
        map_center = sel_info["pos"]
        zoom = 8

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="CartoDB dark_matter", min_zoom=6)
    folium.TileLayer(
        tiles="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        attr="OpenRailwayMap",
        name="Rail Network",
        overlay=True,
        opacity=0.4,
    ).add_to(m)

    for name, info in data.items():
        if not info.get("pos"):
            continue
        is_selected = name == selected_station
        color = get_traffic_color(info["avg_delay"])
        # Brighter, opaque markers (flattened glow)
        folium.CircleMarker(
            location=info["pos"],
            radius=9 if is_selected else 7,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            opacity=0.95,
            weight=2,
            tooltip=f"{name} (+{info['avg_delay']:.0f}min)",
        ).add_to(m)

    if selected_station and selected_station in data:
        info = data[selected_station]
        start = info["pos"]
        for train in info["details"]:
            end = train.get("dest_coords")
            if not end:
                continue
            real_shape = train.get("real_shape") or train.get("cached_shape")
            line_color = get_traffic_color(train["delay"])
            tooltip_text = f"{train['line']} {selected_station} -> {train['to']} (+{train['delay']:.0f} min)"
            if real_shape:
                folium.PolyLine(
                    locations=real_shape,
                    color=line_color,
                    weight=3,
                    opacity=0.9,
                    dash_array="6,10",
                    tooltip=tooltip_text,
                ).add_to(m)
            else:
                folium.PolyLine(
                    locations=[start, end],
                    color=line_color,
                    weight=3,
                    opacity=0.9,
                    dash_array="6,10",
                    tooltip=tooltip_text,
                ).add_to(m)

    output = st_folium(m, width=1400, height=800, key="folium_map")
    if output.get("last_object_clicked"):
        clicked = output["last_object_clicked"]
        tooltip = clicked.get("tooltip")
        if tooltip:
            name = tooltip.split(" (")[0]
            if name in data and st.session_state.get("selected_station") != name:
                st.session_state["selected_station"] = name
                st.rerun()


def render_data_insights(data: dict) -> None:
    st.markdown("### 📊 NETWORK RESILIENCE INTELLIGENCE")
    if not data:
        st.info("No data available.")
        return

    table_rows = []
    for name, info in data.items():
        table_rows.append(
            {
                "Station": name,
                "PageRank": info["rank"],
                "Delay (min)": info["avg_delay"],
                "Latency (min)": info["avg_delay"],
                "Impact Score": info["impact"],
            }
        )
    df = pd.DataFrame(table_rows).sort_values(by="Impact Score", ascending=False)
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("💥 Critical Nodes Ranking")
        try:
            styled = df.style.background_gradient(subset=["Impact Score"], cmap="Reds")
            st.dataframe(styled, use_container_width=True)
        except Exception:
            st.dataframe(df, use_container_width=True)
    with c2:
        st.subheader("📉 Delay Distribution")
        chart_df = df[["Station", "Delay (min)"]]
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("Station:N", axis=alt.Axis(labels=False, title=None, ticks=False)),
                y=alt.Y("Delay (min):Q", title="Delay (min)"),
                tooltip=["Station", "Delay (min)"],
            )
            .properties(width="container", height=240)
        )
        st.altair_chart(chart, use_container_width=True)


def main() -> None:
    if "mode" not in st.session_state:
        st.session_state["mode"] = "🗺️ TACTICAL MAP (2D)"
    if "selected_station" not in st.session_state:
        st.session_state["selected_station"] = None

    sidebar = st.sidebar.container()
    with sidebar:
        sync_clicked, mode_choice = render_sidebar_header(st.session_state["mode"])

    if mode_choice != st.session_state["mode"]:
        st.session_state["mode"] = mode_choice

    if sync_clicked:
        fetch_realtime_data.clear()

    try:
        api, system = load_static_resources()
        data = fetch_realtime_data(api, system)
    except Exception as exc:  # noqa: BLE001
        st.error(f"数据加载异常: {exc}")
        data = {}

    with sidebar:
        render_sidebar_station_section(data, st.session_state["mode"])

    if not data:
        st.warning("没有可用的实时数据。请稍后重试。")
        return

    mode = st.session_state["mode"]
    if mode == "🗺️ TACTICAL MAP (2D)":
        st.header("TACTICAL MAP (2D)")
        render_map(data)
    elif mode == "🌐 GLOBAL HOLOGRAPH (3D)":
        st.header("GLOBAL HOLOGRAPH (3D)")
        st.caption("Visualizing long-distance connections and delay propagation.")
        if "train_anim_t" not in st.session_state:
            st.session_state["train_anim_t"] = 0.0

        selected_station = st.session_state.get("selected_station")
        global_overview = selected_station is None

        if global_overview:
            animate = False
            st.session_state["train_anim_t"] = 0.0
            st.caption("Global overview: animation disabled. Select a station to animate trains.")
        else:
            animate = st.checkbox("Animate trains", value=True, key="animate_trains")
            speed = st.slider("⏱️ Animation speed", 0.002, 0.08, 0.015, step=0.002, key="animate_speed")

        t_val = st.session_state["train_anim_t"]
        if animate:
            t_val = (t_val + speed) % 1.0
            st.session_state["train_anim_t"] = t_val
        else:
            t_val = 0.0
            st.session_state["train_anim_t"] = t_val

        deck = create_3d_map(data, selected_station, t=t_val)
        st.pydeck_chart(deck)

        if animate:
            time.sleep(0.03)
            st.rerun()
    else:
        render_data_insights(data)


if __name__ == "__main__":
    main()
