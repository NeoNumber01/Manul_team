import pydeck as pdk


def create_3d_map(station_data, selected_station=None, t: float = 0.0):
    """
    Animated 3D map with ArcLayer + moving train icons along routes.
    `t` is a 0-1 fraction indicating progress of the animation frame.
    """
    arc_data = []
    train_icon_data = []

    def _lerp(a: float, b: float, frac: float) -> float:
        return a + (b - a) * frac

    for name, info in station_data.items():
        if not info.get("pos"):
            continue

        source_lat, source_lon = info["pos"]
        is_active = name == selected_station

        # If a station is selected — only show its routes
        if selected_station and not is_active:
            continue

        for train in info.get("details", []):
            dest_coords = train.get("dest_coords")
            if not dest_coords:
                continue

            dest_lat, dest_lon = dest_coords
            delay = train.get("delay", 0)

            color = [255, 0, 0] if delay > 10 else [255, 200, 0] if delay > 1 else [0, 255, 128]

            arc_data.append(
                {
                    "from_position": [source_lon, source_lat],
                    "to_position": [dest_lon, dest_lat],
                    "color": color,
                    "name": f"{train['line']} → {train.get('to', '?')} ({delay:.1f} min)",
                    "width": 4 if is_active else 2,
                }
            )

            current_lat = _lerp(source_lat, dest_lat, t)
            current_lon = _lerp(source_lon, dest_lon, t)
            train_icon_data.append(
                {
                    "coordinates": [current_lon, current_lat],
                    "icon": "train",
                    "name": f"{train['line']}",
                }
            )

    arc_layer = pdk.Layer(
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

    icon_layer = pdk.Layer(
        "IconLayer",
        data=train_icon_data,
        get_icon="icon",
        get_position="coordinates",
        get_size=4,
        size_scale=25,
        pickable=True,
        icon_atlas="https://i.imgur.com/xScSkMH.png",
        icon_mapping={
            "train": {
                "x": 0,
                "y": 0,
                "width": 512,
                "height": 512,
                "anchorY": 512,
            }
        },
    )

    view_state = pdk.ViewState(latitude=51.1657, longitude=10.4515, zoom=6, pitch=60, bearing=45)

    if selected_station and selected_station in station_data:
        sel_lat, sel_lon = station_data[selected_station]["pos"]
        view_state = pdk.ViewState(latitude=sel_lat, longitude=sel_lon, zoom=8, pitch=60, bearing=45)

    return pdk.Deck(
        layers=[arc_layer, icon_layer],
        initial_view_state=view_state,
        map_style=pdk.map_styles.CARTO_DARK,
        tooltip={"html": "<b>{name}</b>"},
    )
