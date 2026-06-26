"""Spike front end B: Panel/Solara + Lonboard.

Run: uv run --group panel panel serve apps/panel_lonboard/app.py

Lonboard is an anywidget, so it stays fully interactive inside Panel/Solara
(unlike Streamlit, where it degrades to static to_html). This candidate tests
whether the interactive GeoArrow path is worth a less beginner-friendly shell.
See docs/decisions — the rendering/shell ADR is pending this spike.
"""

# TODO(spike): query gold aggregates via gie.db.connect(), render
#   lonboard.Map([H3HexagonLayer(...), PolygonLayer(admin choropleth)]).
