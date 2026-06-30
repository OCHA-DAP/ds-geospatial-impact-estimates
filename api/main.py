"""FastAPI serving layer for the damage-exposure viewer.

Thin HTTP layer over gie.serving (DuckDB-direct over blob). Serves the
common-model gold (gold/model=common): every source on one Overture building
base, coverage-aware. Responses are GeoJSON / JSON for the deck.gl + MapLibre
front end, cached in memory after first build.

Run: uv run --group api uvicorn api.main:app --reload --port 8077
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from gie.config import load_settings
from gie.serving import (
    export_workbook,
    list_sources,
    load_agreement,
    load_buildings,
    load_common_admin,
    load_common_h3,
    load_coverage_detail,
    load_native,
    load_source_extent,
)

app = FastAPI(title="Damage Exposure API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# API responses are deterministic + read-only until the data is refreshed, so let
# the browser keep its own copy — a reload or revisit is then instant instead of
# re-downloading the (multi-MB) layers. The server-side lru_cache covers repeats
# within a process; this covers the client across page loads. stale-while-
# revalidate keeps revisits instant while a fresh copy is fetched in the
# background. After a data refresh, restarting the app re-reads the new gold;
# clients pick it up within max-age (or on a hard refresh).
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"


def _json(content: str) -> Response:
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": _CACHE_CONTROL},
    )


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


@lru_cache(maxsize=2)
def _agreement_json(adm0: str) -> str:
    return load_agreement(adm0).to_json(orient="records")


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


@app.get("/api/token")
def token() -> dict:
    """Blob read access for the v2 client-side serving path (PMTiles + hyparquet).

    Returns a read SAS + the catalog base URL so the SPA can range-read PMTiles
    and GeoParquet directly from blob. Phase 1 returns the configured read SAS;
    a short-lived user-delegation SAS (managed identity) is a later hardening.
    """
    s = load_settings()
    return {
        "account": s.account_name,
        "container": s.container,
        "base_url": f"https://{s.account_host}/{s.container}/{s.project_prefix}",
        "sas": s.sas_token(write=False),
    }


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


@app.get("/api/agreement")
def agreement(adm0: str = "VE") -> Response:
    return _json(_agreement_json(adm0))


@lru_cache(maxsize=2)
def _coverage_detail_json(adm0: str) -> str:
    return load_coverage_detail(adm0).to_json()


@app.get("/api/coverage_detail")
def coverage_detail(adm0: str = "VE") -> Response:
    return _json(_coverage_detail_json(adm0))


@lru_cache(maxsize=1)
def _export_xlsx(adm0: str) -> bytes:
    return export_workbook(adm0)


@app.get("/api/export.xlsx")
def export_xlsx(adm0: str = "VE") -> Response:
    """Per-admin-unit, per-source damage table — one sheet per admin level."""
    return Response(
        _export_xlsx(adm0),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; "
            "filename=ven_earthquake_damage_compilation_by_admin.xlsx"
        },
    )


# Serve the built SPA (web/dist) at the root, mounted AFTER all /api routes so it
# only catches everything else. In local dev the dist may not exist (Vite serves
# it on :5173), so mount only when present.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
