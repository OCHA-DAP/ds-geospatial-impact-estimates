"""Spike front end A: Streamlit + pydeck.

Run: uv run --group streamlit streamlit run apps/streamlit_pydeck/app.py

Renders the gold damage facts as a pydeck H3HexagonLayer + adm2 outline, with a
metric selector and the source-comparison table. Shares all queries with the
Lonboard app via gie.serving, so the two differ only in rendering.
"""

from __future__ import annotations

import h3
import numpy as np
import pydeck as pdk
import streamlit as st

from gie.serving import damage_colors, load_adm2_damage, load_h3_damage

st.set_page_config(page_title="Damage Exposure — pydeck", layout="wide")
st.title("Damage exposure — Streamlit + pydeck (spike A)")
st.caption("Microsoft predicted building damage, Catia La Mar (Venezuela). Source: HDX, CC-BY.")


@st.cache_data
def _load():
    return load_h3_damage(), load_adm2_damage()


h3df, adm2 = _load()

metric = st.radio(
    "Color hexes by",
    ["damaged_fraction", "buildings_damaged", "buildings_total"],
    horizontal=True,
)

h3df = h3df.copy()
vals = h3df[metric].astype(float)
if metric == "damaged_fraction":
    shade = vals
else:
    shade = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9)
h3df["fill_color"] = damage_colors(shade).tolist()

lats, lons = zip(*[h3.cell_to_latlng(c) for c in h3df["h3"]], strict=False)
view = pdk.ViewState(latitude=float(np.mean(lats)), longitude=float(np.mean(lons)), zoom=12)

hex_layer = pdk.Layer(
    "H3HexagonLayer",
    h3df,
    get_hexagon="h3",
    get_fill_color="fill_color",
    pickable=True,
    extruded=False,
    opacity=0.55,
)
adm2_layer = pdk.Layer(
    "GeoJsonLayer",
    adm2[["geometry"]].__geo_interface__,
    stroked=True,
    filled=False,
    get_line_color=[40, 40, 40],
    line_width_min_pixels=1,
)
deck = pdk.Deck(
    layers=[adm2_layer, hex_layer],
    initial_view_state=view,
    map_provider="carto",
    map_style="light",
    tooltip={"text": "buildings: {buildings_total}\ndamaged: {buildings_damaged}"},
)
st.pydeck_chart(deck)

st.subheader("Admin-2 damage facts (source-comparison shape)")
st.dataframe(
    adm2.drop(columns="geometry").dropna(subset=["buildings_total"]),
    hide_index=True,
)
