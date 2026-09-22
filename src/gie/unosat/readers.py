"""Layer readers and content hashing for UNOSAT silver (spec §3, `readers.py`).

Reads one layer — a GDB feature class or a shapefile inside a zip — into a
GeoDataFrame, reprojects it to WGS84, and computes a deterministic content
hash so a layer re-shipped byte-for-byte identically across many HDX zips
(the same reasoning as bronze's content addressing, see `domains.py`) is
recognised as the same silver object regardless of row order or which
archive it came from.

`extract_gdbs` is NOT redefined here: it is `domains.extract_gdbs`, imported
and re-exported so callers can reach it via either module without the
extraction logic existing in two places.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from gie.unosat.domains import extract_gdbs

__all__ = [
    "extract_gdbs",
    "read_gdb_layer",
    "read_shp_member",
    "to_wgs84",
    "attrs_json",
    "content_hash",
    "HASH_EXCLUDE",
]

# File-layout artefacts: present verbatim in the stored attrs_json (they are
# real attributes of the exported layer), but excluded from the content hash
# so the same polygons re-exported with fresh OBJECTIDs/recomputed
# SHAPE_Area|Length hash identically instead of looking like different content.
# Matched case-insensitively against column names: GDB exports name the field
# `Shape_Length`, shapefiles truncate it to `Shape_Leng`, and casing otherwise
# varies by exporter.
HASH_EXCLUDE = frozenset(
    s.lower() for s in ("shape_length", "shape_leng", "shape_area", "objectid", "fid")
)


def read_gdb_layer(gdb_path: Path, layer: str) -> gpd.GeoDataFrame:
    """Read one feature class from an extracted `.gdb` via GDAL's OpenFileGDB driver."""
    return pyogrio.read_dataframe(gdb_path, layer=layer)


def read_shp_member(zip_path: Path, member: str) -> gpd.GeoDataFrame:
    """Read one `.shp` member directly out of a zip, without extracting it."""
    return pyogrio.read_dataframe(f"zip://{zip_path}!{member}")


def to_wgs84(gdf: gpd.GeoDataFrame, layer: str) -> tuple[gpd.GeoDataFrame, str]:
    """Reproject `gdf` to EPSG:4326, returning `(gdf_4326, source_crs_string)`.

    Raises `ValueError` naming `layer` when the layer carries no CRS at all —
    a missing CRS is an upstream data problem, not something to guess past.
    A layer already in EPSG:4326 is returned unchanged, still reporting
    "EPSG:4326" as its source CRS (a real no-op, not a special case in the
    return value).
    """
    if gdf.crs is None:
        raise ValueError(f"layer {layer!r} has no CRS")
    source_crs = gdf.crs.to_string()
    if gdf.crs.to_epsg() == 4326:
        return gdf, source_crs
    return gdf.to_crs(epsg=4326), source_crs


def _json_scalar(v: object) -> object:
    """Normalise one attribute value for JSON: missing values (NaN, NaT, None)
    all become `None` so they serialise as valid JSON `null` — plain
    `json.dumps` defaults instead emit bare `NaN`/`NaT` tokens, which are not
    valid JSON and strict parsers (including `json.loads` itself) reject.
    """
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.api.types.is_scalar(v) and pd.isna(v):
        return None
    return v


def attrs_json(row: pd.Series) -> str:
    """JSON-serialise every non-geometry column of one feature row.

    Keys are sorted so the same attributes always produce the same string
    regardless of column order. Values are normalised through `_json_scalar`
    first so NaN/NaT become `null`; `default=str` then covers whatever `json`
    still cannot natively serialise — timestamps (GDB fields come back
    tz-aware UTC; SHP dates may be plain datetimes or strings already) and
    numpy scalar types alike. `allow_nan=False` makes any NaN that slips past
    normalisation raise loudly instead of emitting invalid JSON.
    """
    attrs = {k: _json_scalar(v) for k, v in row.items() if k != "geometry"}
    return json.dumps(attrs, default=str, sort_keys=True, allow_nan=False)


def content_hash(gdf: gpd.GeoDataFrame) -> str:
    """Deterministic sha256 over a layer's content, independent of row order
    and of file-layout artefacts (`HASH_EXCLUDE`) that vary across otherwise
    identical exports of the same polygons.

    For each feature: `f"{wkb_hex}|{attrs_json}"`, attrs restricted to the
    non-excluded columns. The per-feature strings are sorted before hashing
    so row order never affects the result.
    """
    drop = [c for c in gdf.columns if c.lower() in HASH_EXCLUDE]
    hashable = gdf.drop(columns=drop) if drop else gdf
    parts = [
        f"{row.geometry.wkb_hex}|{attrs_json(row)}" for _, row in hashable.iterrows()
    ]
    digest_input = "".join(sorted(parts))
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
