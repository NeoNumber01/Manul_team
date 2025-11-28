import pydeck as pdk


def create_3d_map(station_data, selected_station=None):
    """
    Generate PyDeck 3D Map (English Version)
    """
    station_layers_data = []
    path_layers_data = []

    # 1. Prepare Data
    for name, info in station_data.items():
        if not info['pos']: continue

        # Transform coords (Lat, Lon) -> (Lon, Lat)
        lat, lon = info['pos']

        # Color logic
        delay = info['avg_delay']
        if delay < 1:
            color = [0, 255, 128]  # Green
        elif delay < 10:
            color = [255, 200, 0]  # Yellow
        else:
            color = [255, 0, 0]  # Red

        # Radius logic
        radius = 2000 if name == selected_station else 500

        station_layers_data.append({
            "name": name,
            "coordinates": [lon, lat],
            "color": color,
            "radius": radius,
            "delay": f"{delay:.1f} min"
        })

        # Line logic
        is_active = (name == selected_station)
        if selected_station and not is_active:
            continue

        for train in info['details']:
            if not train['dest_coords']: continue

            real_shape = train.get('real_shape')
            dest_lat, dest_lon = train['dest_coords']

            path = []
            if real_shape:
                path = [[p[1], p[0]] for p in real_shape]
            else:
                path = [[lon, lat], [dest_lon, dest_lat]]

            line_color = [255, 50, 50] if train['delay'] > 5 else [0, 200, 255]
            width = 80 if is_active else 30

            path_layers_data.append({
                "path": path,
                "color": line_color,
                "name": f"{train['line']} -> {train['to']}",
                "width": width
            })

    # 2. Define Layers
    layer_stations = pdk.Layer(
        "ScatterplotLayer",
        station_layers_data,
        get_position="coordinates",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.9,
        filled=True
    )

    layer_paths = pdk.Layer(
        "PathLayer",
        path_layers_data,
        get_path="path",
        get_color="color",
        get_width="width",
        width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    )

    # 3. View State
    view_state = pdk.ViewState(
        latitude=51.1657, longitude=10.4515, zoom=6, pitch=45, bearing=0
    )

    if selected_station and selected_station in station_data:
        sel_lat, sel_lon = station_data[selected_station]['pos']
        view_state = pdk.ViewState(
            latitude=sel_lat, longitude=sel_lon, zoom=8, pitch=50, bearing=20
        )

    # 4. Render Deck
    r = pdk.Deck(
        layers=[layer_paths, layer_stations],
        initial_view_state=view_state,
        map_style=pdk.map_styles.CARTO_DARK,
        # Translated Tooltip
        tooltip={"html": "<b>{name}</b><br/>Avg Delay: {delay}"}
    )

    return r