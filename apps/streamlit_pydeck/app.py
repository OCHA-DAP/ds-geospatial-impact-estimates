"""Spike front end A: Streamlit + pydeck.

Run: uv run --group streamlit streamlit run apps/streamlit_pydeck/app.py

Goal of the spike: render the same H3 damage-aggregation layer + admin
choropleth as the Panel/Lonboard candidate, against real Venezuela footprints,
and compare render capacity, interactivity, dev effort, and deployability.
See docs/decisions — the rendering/shell ADR is pending this spike.
"""

# TODO(spike): query gold aggregates via gie.db.connect(), render
#   pydeck.Layer("H3HexagonLayer", ...) + an admin choropleth in st.pydeck_chart.
