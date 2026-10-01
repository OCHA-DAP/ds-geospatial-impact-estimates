"""Build the display rows of the flood-label platinum catalog from the two golds.

The catalog is one thin **display** product over two corpora whose golds differ:

* CEMS gold v1 (ADR-0029): per label set one flood ``geometry`` and one
  ``valid_geometry``; index columns ``area_km2``, ``sensor``... no
  ``label_source``, no water geometry, no ``sensor_class``.
* UNOSAT gold v2 (ADR-0034): ``geom_water`` / ``geom_flood`` /
  ``geom_possible`` / ``geom_valid``; index carries ``label_source``,
  ``sensor_class``, ``water_area_km2``, ``flood_area_km2``.

Nothing is fabricated to make them look alike: a CEMS row has a null
``sensor_class`` and a null ``water_area_km2``; a UNOSAT row whose source never
separated flood (``geom_flood`` null) simply has no flood row. What each source
mapped is what the viewer draws.

Three display collections (one row per label set that has that geometry):

* ``water``  — UNOSAT ``geom_water`` (everything wet at acquisition)
* ``flood``  — UNOSAT ``geom_flood`` where non-null and non-empty, plus every
  CEMS ``geometry`` (CEMS labels *are* flood extents)
* ``masks``  — the analysed-area masks of both

plus ``label-index``, the union of both indexes cut down to :data:`INDEX_COLS`.

Geometry is simplified for display only; full fidelity stays in gold.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely

SOURCES = ("cems", "unosat")
GOLD = {"cems": "copernicus_ems/flood/gold", "unosat": "unosat/gold"}
HDX_DATASETS = "unosat/bronze/_meta/datasets.parquet"

# Display simplification tolerance in degrees, per source. CEMS is analyst
# vector work: 1e-4 (~10 m) keeps the shoreline character. UNOSAT polygons are
# polygonised rasters (ADR-0036): every vertex is a pixel corner, so a
# tolerance below the pixel size removes nothing; 3e-4 (~33 m) flattens the
# 10-30 m staircases and leaves the 375 m VIIRS products untouched.
SIMPLIFY = {"cems": 1e-4, "unosat": 3e-4}
SIMPLIFY_MASK = 5e-4

KEY = ["code", "aoi", "acq_start", "acq_end"]

# The two sources spell three countries differently (CEMS uses the portal's
# short names, HDX the UN long forms). One display name each, mapped
# explicitly; anything not listed is kept exactly as the source wrote it.
COUNTRY_ALIASES = {
    "Bolivia (Plurinational State of)": "Bolivia",
    "Iran (Islamic Republic of)": "Iran",
    "Myanmar/Burma": "Myanmar",
}

# Acquisition dates before this are not dates: the index is checked and the
# offending rows are REPORTED (build summary), never dropped or corrected here.
EARLIEST_PLAUSIBLE = pd.Timestamp("2005-01-01")

INDEX_COLS = [
    "label_source",
    "code",
    "name",
    "countries",
    "aoi",
    "acq_start",
    "acq_end",
    "label_day",
    "sensor",
    "sensor_class",
    "acq_method",
    "acq_precision",
    "water_area_km2",
    "flood_area_km2",
    "valid_basis",
    "minx",
    "miny",
    "maxx",
    "maxy",
]

# What rides on every tile feature (the popup and the step list read these).
TILE_ATTRS = [
    "label_source",
    "code",
    "aoi",
    "acq_start",
    "acq_end",
    "label_day",
    "sensor",
    "sensor_class",
    "acq_method",
    "acq_precision",
]

_CEMS_INDEX_REQUIRED = [
    "code",
    "name",
    "countries",
    "aoi",
    "acq_start",
    "acq_end",
    "label_day",
    "sensor",
    "acq_method",
    "acq_precision",
    "area_km2",
    "valid_basis",
    "minx",
    "miny",
    "maxx",
    "maxy",
]
_UNOSAT_INDEX_REQUIRED = [
    "label_source",
    "code",
    "name",
    "countries",
    "aoi",
    "acq_start",
    "acq_end",
    "label_day",
    "sensor",
    "sensor_class",
    "acq_method",
    "acq_precision",
    "water_area_km2",
    "flood_area_km2",
    "valid_basis",
    "minx",
    "miny",
    "maxx",
    "maxy",
]

# Geometry columns read per source: collection -> gold column.
GEOMETRY_COLUMNS = {
    "cems": {"flood": "geometry", "masks": "valid_geometry"},
    "unosat": {"water": "geom_water", "flood": "geom_flood", "masks": "geom_valid"},
}
LABEL_KEYS = {
    "cems": ["code", "aoi", "acq_start", "acq_end"],
    "unosat": ["code", "aoi", "acq_start", "acq_end"],
}


# --- paths -----------------------------------------------------------------


def index_path(source: str) -> str:
    _check_source(source)
    return f"{GOLD[source]}/label_index.parquet"


def labels_prefix(source: str) -> str:
    _check_source(source)
    return f"{GOLD[source]}/labels/code="


def labels_path(source: str, code: str) -> str:
    return f"{labels_prefix(source)}{code}/data.parquet"


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"unknown label source {source!r}; expected one of {SOURCES}")


# --- index -----------------------------------------------------------------


def harmonise_index(
    source: str, idx: pd.DataFrame, hdx_datasets: pd.DataFrame | None = None
) -> pd.DataFrame:
    """One source's gold index -> the display index columns.

    CEMS: ``flood_area_km2`` is v1's ``area_km2``; ``sensor_class`` and
    ``water_area_km2`` are null (v1 does not carry them — not derived here).
    UNOSAT: ``countries`` are ISO3 in gold; the display wants names, and the
    HDX dataset record (``hdx_datasets``, joined on ``name``) is the source's
    own naming, so that is what is used. A name with no HDX record raises.
    """
    _check_source(source)
    required = _CEMS_INDEX_REQUIRED if source == "cems" else _UNOSAT_INDEX_REQUIRED
    missing = [c for c in required if c not in idx.columns]
    if missing:
        raise KeyError(f"{source} label_index is missing columns {missing}")
    out = idx.copy()
    if source == "cems":
        out["label_source"] = "cems"
        out["sensor_class"] = None
        out["water_area_km2"] = np.nan
        out["flood_area_km2"] = out["area_km2"]
    else:
        bad = sorted(set(out["label_source"]) - {"unosat"})
        if bad:
            raise ValueError(f"unosat label_index carries label_source values {bad}")
        if hdx_datasets is None:
            raise ValueError("unosat index needs hdx_datasets to resolve country names")
        out["countries"] = _hdx_country_names(out["name"], hdx_datasets)
    out["countries"] = out["countries"].map(_alias_countries)
    out["acq_start"] = pd.to_datetime(out["acq_start"]).astype("datetime64[us]")
    out["acq_end"] = pd.to_datetime(out["acq_end"]).astype("datetime64[us]")
    out["label_day"] = out["label_day"].astype("string")
    out["aoi"] = out["aoi"].fillna("").astype(str)
    return out[INDEX_COLS].reset_index(drop=True)


def _alias_countries(value) -> str:
    """Apply COUNTRY_ALIASES to a ';'-separated country list."""
    parts = [p.strip() for p in str(value).split(";") if p.strip()]
    return "; ".join(COUNTRY_ALIASES.get(p, p) for p in parts)


def implausible_dates(index: pd.DataFrame) -> pd.DataFrame:
    """Index rows whose acquisition interval starts before EARLIEST_PLAUSIBLE.
    A gold defect to report, not to hide: the viewer's timeline simply cannot
    place them, and the fusion reader must not trust them either."""
    bad = index[(index["acq_start"] < EARLIEST_PLAUSIBLE) | (index["acq_end"] < EARLIEST_PLAUSIBLE)]
    return bad[["label_source", "code", "aoi", "acq_start", "acq_end", "acq_method", "sensor"]]


def _hdx_country_names(names: pd.Series, hdx_datasets: pd.DataFrame) -> pd.Series:
    for c in ("dataset_name", "countries"):
        if c not in hdx_datasets.columns:
            raise KeyError(f"hdx datasets table is missing column {c!r}")
    by_name = hdx_datasets.drop_duplicates("dataset_name").set_index("dataset_name")["countries"]
    unknown = sorted(set(names) - set(by_name.index))
    if unknown:
        raise KeyError(
            f"{len(unknown)} unosat label_index names have no HDX dataset record: {unknown[:5]}"
        )
    return names.map(by_name).astype(str).to_numpy()


def combine_index(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate harmonised indexes; the display key must be unique."""
    if not frames:
        raise ValueError("no index frames to combine")
    out = pd.concat(frames, ignore_index=True)
    key = ["label_source", *KEY]
    dup = out[out.duplicated(key, keep=False)]
    if len(dup):
        raise ValueError(
            f"{len(dup)} index rows share a display key; first: {dup[key].iloc[0].to_dict()}"
        )
    return out


def index_geometry(index: pd.DataFrame) -> list:
    """A bbox polygon per index row for the GeoParquet index, or None where
    the row has no bbox: a label set whose every geometry is null (every
    polygon an excluded kind, or a flood layer that found nothing) has no
    extent, and a display index must say so rather than invent one."""
    out = []
    for r in index[["minx", "miny", "maxx", "maxy"]].itertuples(index=False):
        vals = (r.minx, r.miny, r.maxx, r.maxy)
        out.append(None if any(pd.isna(v) for v in vals) else shapely.box(*vals))
    return out


# --- display rows ------------------------------------------------------------


def simplify(geom, tolerance: float):
    """Display simplification: Douglas-Peucker without topology preservation,
    applied PART BY PART, polygons only.

    Measured on FL20210928THA's largest row (3.7M vertices, 55,904 parts):
    GEOS's simplifier on the whole MultiPolygon took 56.4 s; the same call
    vectorised over its exploded parts took 0.4 s for the same 373k output
    vertices. Whatever the multipolygon path does per part, we do not need it.
    Tiles are rendered with the even-odd rule, so a self-touch does not show.

    CEMS v1 geometries can be GeometryCollections (make_valid leaves line
    fragments next to the polygons); only polygonal parts have an area to draw,
    so the others are left out. A label set the tolerance collapses entirely
    keeps its original shape rather than disappearing; a collapsed part next to
    drawable ones is left out.
    """
    parts = polygon_parts(geom)
    if len(parts) == 0:
        return geom
    out = shapely.simplify(parts, tolerance, preserve_topology=False)
    bad = shapely.is_empty(out) | (shapely.get_type_id(out) != shapely.GeometryType.POLYGON)
    if bad.all():  # noqa: SIM108 (the two branches deserve their comments)
        # smaller than the tolerance in every part: draw it as it is rather
        # than not at all (a label set must not vanish from the map)
        out = parts
    else:
        # sub-tolerance parts next to drawable ones are below what the tiles
        # can show; keeping them at full detail only inflates the catalog
        out = out[~bad]
    if len(out) == 1:
        return out[0]
    return shapely.multipolygons(out)


def polygon_parts(geom) -> np.ndarray:
    """Every Polygon inside ``geom``, however nested (MultiPolygon, or a
    GeometryCollection holding MultiPolygons); non-polygonal parts dropped."""
    parts = shapely.get_parts(geom)
    while True:
        multi = shapely.get_type_id(parts) >= shapely.GeometryType.MULTIPOINT
        if not multi.any():
            break
        parts = np.concatenate([parts[~multi], shapely.get_parts(parts[multi])])
    return parts[shapely.get_type_id(parts) == shapely.GeometryType.POLYGON]


def read_geometry_column(
    path: Path | io.BytesIO, keys: list[str], column: str
) -> tuple[pd.DataFrame, np.ndarray]:
    """One geometry column of a gold labels file, decoded from WKB, with its
    key columns. Column-at-a-time so a 2 GB labels file (FL20200713BGD:
    ~1 GB of water and ~1 GB of flood WKB) never has to be in memory whole."""
    # ParquetFile, not read_table: the file sits under `code={EventCode}/` AND
    # carries a `code` column, and read_table's hive-partition inference then
    # refuses to merge the two (the same trap gold.read_labels_file avoids).
    table = pq.ParquetFile(path).read(columns=[*keys, column])
    frame = table.select(keys).to_pandas()
    wkb = table.column(column).to_numpy(zero_copy_only=False)
    geoms = shapely.from_wkb(wkb)
    return frame, geoms


def display_rows(
    source: str, path: Path | io.BytesIO, index: pd.DataFrame
) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """The display rows of one code's labels file, per collection, with the
    index attributes attached.

    Every labels row must have exactly one index row (same key); anything
    else raises — a label set the index does not know is a gold defect, not
    something to draw silently. Returns ``(rows, counts)`` where ``counts``
    says how many label sets had no geometry in each collection, so the run
    summary can report absence rather than lose it.
    """
    _check_source(source)
    keys = LABEL_KEYS[source]
    src_index = index[index["label_source"] == source]
    keyed = src_index.set_index(KEY, drop=False)
    if not keyed.index.is_unique:
        raise ValueError(f"{source} display index is not unique on {KEY}")
    rows: dict[str, list[dict]] = {"water": [], "flood": [], "masks": []}
    counts: dict[str, int] = {}
    for collection, column in GEOMETRY_COLUMNS[source].items():
        frame, geoms = read_geometry_column(path, keys, column)
        frame["acq_start"] = pd.to_datetime(frame["acq_start"]).astype("datetime64[us]")
        frame["acq_end"] = pd.to_datetime(frame["acq_end"]).astype("datetime64[us]")
        frame["aoi"] = frame["aoi"].fillna("").astype(str)
        absent = 0
        tol = SIMPLIFY_MASK if collection == "masks" else SIMPLIFY[source]
        for i, r in enumerate(frame.itertuples(index=False)):
            key = (r.code, r.aoi, r.acq_start, r.acq_end)
            if key not in keyed.index:
                raise ValueError(f"{source} {r.code}: labels row {key} has no index row")
            meta = keyed.loc[key]
            if isinstance(meta, pd.DataFrame):
                raise ValueError(f"{source} {r.code}: index has several rows for {key}")
            geom = geoms[i]
            if geom is None or geom.is_empty:
                absent += 1
                continue
            row = _attrs(meta, collection)
            row["geometry"] = simplify(geom, tol)
            rows[collection].append(row)
        counts[f"{collection}_absent"] = absent
        del frame, geoms
    return rows, counts


def _attrs(meta: pd.Series, collection: str) -> dict:
    row = {c: _plain(meta[c]) for c in TILE_ATTRS}
    if collection == "masks":
        row["valid_basis"] = _plain(meta["valid_basis"])
    else:
        area = "water_area_km2" if collection == "water" else "flood_area_km2"
        row["area_km2"] = _plain(meta[area])
    return row


def _plain(value):
    """Tile attributes: timestamps as ISO strings (the page compares them as
    strings), NaN/NA as None, numpy scalars as Python."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value
