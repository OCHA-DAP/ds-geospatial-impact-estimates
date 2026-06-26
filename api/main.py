"""FastAPI serving layer for the damage-exposure viewer.

Thin HTTP layer over gie.serving (DuckDB-direct over blob). Serves the
common-model gold (gold/model=common): every source on one Overture building
base, coverage-aware. Responses are GeoJSON / JSON for the deck.gl + MapLibre
front end, cached in memory after first build.

Run: uv run --group api uvicorn api.main:app --reload --port 8077
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from gie.serving import (
    list_sources,
    load_buildings,
    load_common_admin,
    load_common_h3,
    load_native,
    load_source_extent,
)

app = FastAPI(title="Damage Exposure API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _json(content: str) -> Response:
    return Response(content=content, media_type="application/json")


@lru_cache(maxsize=1)
def _sources(adm0: str) -> list[str]:
    return list_sources(adm0)


@lru_cache(maxsize=16)
def _common_h3_json(source: str, adm0: str) -> str:
    return load_common_h3(source, adm0).to_json(orient="records")


@lru_cache(maxsize=32)
def _common_admin_json(level: int, source: str, adm0: str) -> str:
    return load_common_admin(level, source, adm0).to_json()


@lru_cache(maxsize=8)
def _buildings_json(source: str, adm0: str) -> str:
    return load_buildings(source, adm0).to_json(orient="records")


@lru_cache(maxsize=8)
def _native_json(source: str, adm0: str) -> str:
    return load_native(source, adm0).to_json()


@lru_cache(maxsize=8)
def _extent_json(source: str, adm0: str) -> str:
    return load_source_extent(source, adm0).to_json()


# Metrics available on the common model, in display order (label shown in the UI).
METRICS = [
    {"key": "damaged_detected", "label": "Damaged buildings"},
    {"key": "damaged_extrapolated", "label": "Damaged buildings (estimated)"},
    {"key": "coverage_fraction", "label": "Coverage"},
    {"key": "exposed_buildings", "label": "Total buildings"},
]


@app.get("/api/sources")
def sources(adm0: str = "VE") -> dict:
    return {"sources": _sources(adm0), "adm0": adm0, "metrics": METRICS}


@app.get("/api/common/h3")
def common_h3(source: str, adm0: str = "VE") -> Response:
    return _json(_common_h3_json(source, adm0))


@app.get("/api/common/admin/{level}")
def common_admin(level: int, source: str, adm0: str = "VE") -> Response:
    return _json(_common_admin_json(level, source, adm0))


@app.get("/api/buildings")
def buildings(source: str, adm0: str = "VE") -> Response:
    return _json(_buildings_json(source, adm0))


@app.get("/api/native")
def native(source: str, adm0: str = "VE") -> Response:
    return _json(_native_json(source, adm0))


@app.get("/api/extent")
def extent(source: str, adm0: str = "VE") -> Response:
    return _json(_extent_json(source, adm0))
