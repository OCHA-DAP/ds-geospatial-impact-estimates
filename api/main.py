"""FastAPI serving layer for the damage-exposure viewer.

Thin HTTP layer over gie.serving (DuckDB-direct over blob). Responses are
GeoJSON / JSON for the deck.gl + MapLibre front end. Each payload is cached in
memory after first build, since the underlying blob reads take a second or two.

Run: uv run --group api uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from gie.serving import load_admin_damage, load_footprints, load_h3_damage

app = FastAPI(title="Damage Exposure API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _json(content: str) -> Response:
    return Response(content=content, media_type="application/json")


@lru_cache(maxsize=16)
def _h3_json(source: str, adm0: str) -> str:
    return load_h3_damage(source, adm0).to_json(orient="records")


@lru_cache(maxsize=16)
def _admin_json(level: int, source: str, adm0: str) -> str:
    return load_admin_damage(level, source, adm0).to_json()


@lru_cache(maxsize=8)
def _footprints_json(source: str, adm0: str) -> str:
    return load_footprints(source, adm0).to_json()


@app.get("/api/sources")
def sources() -> dict:
    # Static for now; later derive from gold partitions in blob.
    return {"sources": ["microsoft"], "adm0": ["VE"]}


@app.get("/api/h3")
def h3(source: str = "microsoft", adm0: str = "VE") -> Response:
    return _json(_h3_json(source, adm0))


@app.get("/api/admin/{level}")
def admin(level: int, source: str = "microsoft", adm0: str = "VE") -> Response:
    return _json(_admin_json(level, source, adm0))


@app.get("/api/footprints")
def footprints(source: str = "microsoft", adm0: str = "VE") -> Response:
    return _json(_footprints_json(source, adm0))
