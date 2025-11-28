import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

# === PROJECT IMPORTS ===
from data.api_client import TransportAPI
from src.gtfs_loader import load_stops_from_gtfs_zip, load_stop_times_from_gtfs_zip
from src.graph_builder import build_graph
from src.graph_cache import load_graph_cache, save_graph_cache
from src.ranking import compute_pagerank_and_risk
from src.routing import shortest_path_fastest, path_total_time


# ================================================================
# STREAMLIT CONFIG
# ================================================================
st.set_page_config(layout="wide", page_title="Hybrid Transit Intelligence 2.0")
st.title("🟩 Hybrid Transit Intelligence — Real-Time DB + GTFS Graph + Routing")

st.markdown("""
### Features:
- 📡 Transport REST API (Germany)  
- 🚌 Full GTFS graph (all stations)  
- 🧠 PageRank-based station importance  
- 🚦 Impact = delay × PageRank  
- 🗺 Routing (GTFS From → To)  
""")


# ================================================================
# 1. LOAD GTFS
# ================================================================
st.header("1. Load GTFS Data")

gtfs_path = "data/gtfs.zip"

stops_df = load_stops_from_gtfs_zip(gtfs_path)
stop_times_df = load_stop_times_from_gtfs_zip(gtfs_path)

# Remove platform entries
stops_df = stops_df[stops_df["location_type"] != 1]

station_names = sorted(stops_df["stop_name"].unique().tolist())

st.success(f"GTFS loaded: {len(stops_df)} stations.")


# ================================================================
# 2. LOAD GRAPH
# ================================================================
st.header("2. Build Station Graph")

G = load_graph_cache("data/graph_cache.pkl")

if G is None:
    st.warning("Graph cache not found — building graph…")
    G = build_graph(stops_df, stop_times_df)
    save_graph_cache(G, "data/graph_cache.pkl")
    st.success("Graph built and cached.")
else:
    st.success("Graph loaded from cache.")


# ================================================================
# 3. ROUTING
# ================================================================
st.header("3. Route Search (GTFS Routing)")

col1, col2 = st.columns(2)

with col1:
    from_station = st.selectbox("From:", station_names)

with col2:
    to_station = st.selectbox("To:", station_names)

path = None
from_ids = []

if from_station and to_station:

    from_ids = stops_df[stops_df["stop_name"] == from_station]["stop_id"].tolist()
    to_ids = stops_df[stops_df["stop_name"] == to_station]["stop_id"].tolist()

    if from_ids and to_ids:

        from_id = from_ids[0]
        to_id = to_ids[0]

        path = shortest_path_fastest(G, from_id, to_id)

        if path:
            st.success(f"Route found! Path length: {len(path)} nodes.")
            travel_time = path_total_time(G, path)
            st.info(f"Graph travel weight: {travel_time}")
        else:
            st.error("Route not found.")


# ================================================================
# 4. REAL-TIME (DELAY DATA)
# ================================================================
st.header("4. Real-Time Delays (Transport REST API)")

api = TransportAPI()
station_id = None

# Match GTFS name against known DB API stations
for name, sid in api.target_stations.items():
    if from_station.lower() in name.lower():
        station_id = sid
        break

if station_id:
    avg_delay, details = api.get_realtime_departures(station_id)
    st.metric("Average delay", f"{avg_delay:.1f} min")
else:
    st.info("Selected station is not available in the Transport API list.")


# ================================================================
# 4B. ACTIVE REAL-TIME TRAINS
# ================================================================
st.header("4B. Active Real-Time Trains Along Route")

active_trains = []

if path:
    # Convert stop_ids → names along route
    route_station_names = set()
    for sid in path:
        row = stops_df.loc[stops_df["stop_id"] == sid]
        if not row.empty:
            route_station_names.add(row.iloc[0]["stop_name"])

    # Query only API stations that appear on the route
    for hub_name, hub_id in api.target_stations.items():

        base_name = hub_name.replace(" Hbf", "")
        if any(base_name in name for name in route_station_names):

            avg_d, det = api.get_realtime_departures(hub_id)

            for train in det:
                active_trains.append({
                    "station": hub_name,
                    "line": train["line"],
                    "direction": train["to"],
                    "delay_min": train["delay"],
                    "destination_coords": train["dest_coords"],
                    "polyline": train.get("real_shape")
                })

    if active_trains:
        st.dataframe(pd.DataFrame(active_trains))
    else:
        st.warning("No active trains detected along this route (from monitored stations).")
else:
    st.info("Select a route first.")


# ================================================================
# 5. PageRank + Impact
# ================================================================
st.header("5. Station PageRank Importance")

delay_mapping = []

if path:
    base_delay = avg_delay if station_id else 0.0

    for stop_id in path:
        delay_mapping.append({
            "stop_id": stop_id,
            "delay_minutes": base_delay
        })

df_delay = pd.DataFrame(delay_mapping)

if df_delay.empty:
    st.warning("No delay data available for this route.")
else:
    pagerank_df = compute_pagerank_and_risk(G, df_delay)

    pagerank_df["lat"] = pagerank_df.index.map(lambda s: G.nodes[s].get("lat"))
    pagerank_df["lon"] = pagerank_df.index.map(lambda s: G.nodes[s].get("lon"))

    st.dataframe(pagerank_df.head())


# ================================================================
# 6. MAP VISUALIZATION
# ================================================================
st.header("6. Interactive Map")

center_lat = pagerank_df["lat"].mean()
center_lon = pagerank_df["lon"].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=9)

# PageRank visualization
for stop_id, row in pagerank_df.iterrows():
    if pd.isna(row.lat) or pd.isna(row.lon):
        continue

    folium.CircleMarker(
        location=[row.lat, row.lon],
        radius=5 + row["pagerank"] * 40,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"{row.stop_name} — PR {row.pagerank:.5f}"
    ).add_to(m)

# Draw route path
if path:
    coords = [[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in path]
    folium.PolyLine(coords, color="blue", weight=4, opacity=0.8).add_to(m)

st_folium(m, width=900, height=600)
