import pydeck as pdk


def create_3d_map(station_data, selected_station=None):
    """
    Generate 3D map using ArcLayer for smooth, elevated curved arrows.
    Mirrors the provided Manul implementation.
    """
    arc_data = []

    for name, info in station_data.items():
        if not info["pos"]:
            continue

        source_lat, source_lon = info["pos"]
        is_active = name == selected_station

        # If a station is selected — only show its routes
        if selected_station and not is_active:
            continue

        for train in info["details"]:
            if not train["dest_coords"]:
                continue

            dest_lat, dest_lon = train["dest_coords"]
            delay = train["delay"]

            # Color of the arc based on the delay
            color = [255, 0, 0] if delay > 10 else [255, 200, 0] if delay > 1 else [0, 255, 128]

            arc_data.append(
                {
                    "from_position": [source_lon, source_lat],
                    "to_position": [dest_lon, dest_lat],
                    "color": color,
                    "name": f"{train['line']} {name} → {train['to']} ({delay:.1f} min)",
                    "width": 4 if is_active else 2,
                }
            )

    layer_arcs = pdk.Layer(
        "ArcLayer",
        data=arc_data,
        get_source_position="from_position",
        get_target_position="to_position",
        get_source_color="color",
        get_target_color="color",
        get_width="width",
        width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(latitude=51.1657, longitude=10.4515, zoom=6, pitch=60, bearing=45)

    if selected_station and selected_station in station_data:
        sel_lat, sel_lon = station_data[selected_station]["pos"]
        view_state = pdk.ViewState(latitude=sel_lat, longitude=sel_lon, zoom=8, pitch=60, bearing=45)

    return pdk.Deck(
        layers=[layer_arcs],
        initial_view_state=view_state,
        map_style=pdk.map_styles.CARTO_DARK,
        tooltip={"html": "<b>{name}</b>"},
    )
