---
status: "accepted"
date: 2026-06-26
deciders: data science team
---

# Map-first viewer: a custom deck.gl + MapLibre SPA over a FastAPI serving layer

## Context and Problem Statement

ADR-0002 deferred the rendering/shell choice to a spike. We built two
Python-native candidates — Streamlit + pydeck and Solara + Lonboard — rendering
the same gold facts. On review, neither met the product vision: a **map-first
platform** where the map is the focus, controls/legend/comparison float as
panels over it, and **hover is a primary interaction**. The dashboards put the
map inside a document flow rather than making it the canvas.

## Decision Drivers

* Map is the primary surface; panels float over a full-bleed map.
* Rich, low-latency hover/picking across layers.
* Render adm3 choropleth + H3 + (eventually) raw footprints together.
* Keep the Python backend (lake, DuckDB engine, gold facts) unchanged.

## Considered Options

1. **Custom SPA: MapLibre GL (basemap) + deck.gl (overlay layers), served data
   by a thin FastAPI layer over `gie.serving`.**
2. **Streamlit + pydeck.**
3. **Solara + Lonboard.**

## Decision Outcome

Chosen option: **Option 1**. A MapLibre + deck.gl single-page app is purpose-built
for a map-first UX: full-screen map, floating HTML/CSS panels, and fully custom
deck.gl `onHover` tooltips. A small **FastAPI** app exposes the existing
`gie.serving` queries as GeoJSON/JSON (`/api/admin/{level}`, `/api/h3`,
`/api/footprints`), so the **entire Python backend is reused unchanged** — the
SPA is purely additive on top of DuckDB-over-blob.

The cost is real and accepted: a JavaScript front end (Vite + TypeScript) and a
Node toolchain on a Python-majority team, plus a serving tier we didn't have
before. PMTiles remains the scale-out path for footprint volumes that outgrow
GeoJSON-over-HTTP (not needed at ~30k features).

Streamlit is **rejected**: its top-down document model fights a map-first
layout. Solara + Lonboard is **rejected** for this vision: it *can* do map-first
and is Python-native, but its hover/polish ceiling and widget-lifecycle friction
(import-time `Widget.close_all()` closing default controls) make it the wrong
fit when the map UX is the product.

### Consequences

* Good, because the SPA gives the map-first UX, floating panels, and custom hover.
* Good, because the backend (blob, DuckDB, gold) is untouched; the API is thin.
* Good, because deck.gl scales to the raw-footprint layer the team wants next.
* Bad, because a Python-majority team now maintains a JS/TS front end + Node build.
* Bad, because a serving tier (FastAPI) is new surface to deploy/secure on the
  app service plan.
* Neutral, because client-rendered GeoJSON is fine now but tiling (PMTiles) will
  be needed as footprint volume grows.

## Pros and Cons of the Options

### Option 1 — custom deck.gl + MapLibre SPA

* Good, because it is exactly a map-first, floating-panel, rich-hover app.
* Good, because it reuses the whole Python backend via a thin API.
* Bad, because it adds a JS toolchain and a serving tier.

### Option 2 — Streamlit + pydeck

* Good, because fastest to a basic dashboard; first-class `st.pydeck_chart`.
* Bad, because top-down document flow can't deliver a map-first UX; per-user
  concurrency cost for a public app.

### Option 3 — Solara + Lonboard

* Good, because Python-native and Lonboard's GeoArrow path scales to footprints.
* Bad, because hover/polish ceiling and Solara/Lonboard widget-lifecycle friction
  for a map-centric product.

## More Information

* Spike apps (removed after this decision) live in git history.
* Serving layer: `api/main.py` over `gie.serving`; front end: `web/`.
* Supersedes the "rendering/shell ADR pending spike" note in `0002`.
* Revisit the JS-toolchain trade-off if the team cannot sustain a TS front end;
  a Solara fallback remains viable on the same API/backend.
