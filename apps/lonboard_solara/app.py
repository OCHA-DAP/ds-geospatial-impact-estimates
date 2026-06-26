"""Spike front end B: Solara + Lonboard.

Run: uv run --group lonboard solara run apps/lonboard_solara/app.py

Renders the same gold damage facts as a Lonboard H3HexagonLayer + adm2 outline.
Lonboard keeps the data binary (GeoArrow) end-to-end and stays fully interactive
in Solara (unlike Streamlit, where it degrades to static HTML). Shares all
queries with the pydeck app via gie.serving.
"""

from __future__ import annotations

import solara
from lonboard import H3HexagonLayer, Map, PolygonLayer

from gie.serving import damage_colors, load_adm2_damage, load_h3_damage

# Plain data at module scope is fine; the widgets (layers, Map) must be built
# INSIDE the component — Solara's import-time Widget.close_all() would otherwise
# close any widget created at module import and the session would use dead refs.
h3df = load_h3_damage()
adm2 = load_adm2_damage()


@solara.component
def Page():
    hex_layer = H3HexagonLayer.from_pandas(
        h3df,
        get_hexagon=h3df["h3"],
        get_fill_color=damage_colors(h3df["damaged_fraction"]),
        pickable=True,
        extruded=False,
        opacity=0.55,
    )
    adm2_layer = PolygonLayer.from_geopandas(
        adm2[["geometry"]],
        filled=False,
        stroked=True,
        get_line_color=[40, 40, 40],
        line_width_min_pixels=1,
    )
    # controls=[] avoids Lonboard's default FullscreenControl, which Solara's
    # import-time Widget.close_all() closes (leaving the Map with a dead ref).
    m = Map([adm2_layer, hex_layer], controls=[])
    m.set_view_state(longitude=-67.03, latitude=10.59, zoom=12)
    with solara.Column(style={"min-height": "820px"}):
        solara.Markdown(
            "## Damage exposure — Solara + Lonboard (spike B)\n"
            "Microsoft predicted building damage, Catia La Mar (Venezuela). "
            "Source: HDX, CC-BY."
        )
        solara.display(m)
