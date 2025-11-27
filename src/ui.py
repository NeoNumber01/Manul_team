"""UI helpers for station picking (simple selectbox)."""

from __future__ import annotations

import streamlit as st


def station_picker(
    *,
    title: str,
    options: list[tuple[str, str]],  # (node_key, display_name)
    key_prefix: str,
    default_node: str | None = None,
    max_results: int | None = None,
) -> str | None:
    """Render a single station dropdown (built-in selectbox search on open)."""
    if not options:
        st.warning("No stations available.")
        return None

    options_sorted = sorted(options, key=lambda x: (x[1] or x[0]).casefold())

    # Optional cap to keep UI responsive (if provided).
    if max_results is not None and max_results > 0 and len(options_sorted) > max_results:
        options_sorted = options_sorted[:max_results]

    display_by_key = {k: (name or k) for (k, name) in options_sorted}
    keys = [k for (k, _) in options_sorted]

    # Pick a default index if possible.
    default_index = 0
    if default_node is not None:
        try:
            default_index = keys.index(default_node)
        except ValueError:
            default_index = 0

    selected_key = st.selectbox(
        title,
        options=keys,
        index=default_index,
        key=f"{key_prefix}_station",
        format_func=lambda k: display_by_key.get(k, str(k)),
        help="Tip: open the dropdown and type to search.",
    )
    return selected_key
