"""Gold v2 for the UNOSAT flood archive (spec §4): the shared label schema.

Silver stores one row per polygon. Gold dissolves those rows into **label
sets**: one row per `(label_source, code, area_label, acquisition interval)`
carrying up to three geometries and one validity mask, which is the shape a
training-data reader wants — rasterise the geometries, rasterise the mask,
and treat everything outside the mask as unobserved rather than dry.

**Why three geometries and not one.** UNOSAT ships permanent/pre-flood water,
flood water and possible flood-affected land as separate claims, and the
fusion work needs both targets: `geom_water` (everything wet at acquisition,
the target that is comparable across sensors) and `geom_flood` (the flood
increment, which only sources that separate it can offer). Folding them into
one geometry would make a permanent-water layer and a flood layer
indistinguishable; keeping `geom_flood` null where a source never separated
flood keeps "we don't know" apart from "there was none" — the difference
between a missing label and a negative one.

**What never enters a geometry.** `aggregate_max` / `aggregate_min` are
cumulative extents over a whole activation, not an observation at one
acquisition, and `other_water` is aquaculture, swamp, snow. All three are
dropped from the dissolves and counted in `excluded_aggregate_n`, so the
exclusion is visible per label set rather than implicit in a row count.

**The mask.** `geom_valid` is the analysis footprint for the *same area and
interval* minus what was not analysed (cloud), with `valid_basis` naming
which of the three states produced it. A footprint from another area or
another acquisition is a different observation, so it never stands in: the
honest answer there is `valid_basis = "none"`, not a mask that would call
unobserved ground observed.

CEMS gold is rebuilt to this schema in a follow-up, which is why `INDEX_COLUMNS`
carries `label_source` and the CEMS-only `sensor_gsd` / `det_methods`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon

from gie.unosat import classes, common, grammar, silver
from gie.unosat.store import BlobStore

__all__ = [
    "INDEX_COLUMNS",
    "LABEL_COLUMNS",
    "GEOMETRY_COLUMNS",
    "WATER_KINDS",
    "EXCLUDED_KINDS",
    "build_code",
    "code_meta",
    "labels_path",
    "index_part_path",
    "INDEX_PATH",
    "local_path",
    "read_labels_file",
    "read_partition",
    "iter_index_parts",
    "list_silver_codes",
    "built_codes",
]

WGS84 = "EPSG:4326"
# Equal-area, as CEMS gold uses: km2 that mean the same thing at every latitude.
EQ_AREA = "EPSG:6933"
LABEL_SOURCE = "unosat"

# Everything wet at acquisition, whatever produced it.
WATER_KINDS = ("water", "water_pre", "flood")
FLOOD_KINDS = ("flood",)
POSSIBLE_KINDS = ("flood_possible",)
# Never a geometry; counted instead (see the module docstring).
EXCLUDED_KINDS = ("aggregate_max", "aggregate_min", "other_water")

ACQ_PRECISIONS = ("date", "window", "none")

GEOMETRY_COLUMNS = ("geom_water", "geom_flood", "geom_possible", "geom_valid")

LABEL_COLUMNS = [
    "label_source",
    "code",
    "aoi",
    "acq_start",
    "acq_end",
    "label_day",
    "valid_basis",
    *GEOMETRY_COLUMNS,
]

# Spec §4 "label_index.parquet columns", in that order.
INDEX_COLUMNS = [
    "label_source",
    "code",
    "name",
    "countries",
    "aoi",
    "acq_start",
    "acq_end",
    "width_days",
    "label_day",
    "acq_method",
    "acq_precision",
    "acq_conflict",
    "sensor",
    "sensor_class",
    "sensor_gsd",
    "det_methods",
    "product_classes",
    "confidence",
    "water_status",
    "n_polygons",
    "water_area_km2",
    "flood_area_km2",
    "possible_area_km2",
    "valid_basis",
    "valid_area_km2",
    "minx",
    "miny",
    "maxx",
    "maxy",
    "target_ids",
    "excluded_aggregate_n",
]

# Derived from the dissolved geometries after the frame is built, not per group:
# one reprojection per column beats one per label set.
_AREA_OF = {
    "water_area_km2": "geom_water",
    "flood_area_km2": "geom_flood",
    "possible_area_km2": "geom_possible",
    "valid_area_km2": "geom_valid",
}


# --- preparing the silver frames -------------------------------------------


def _area_labels(frame: pd.DataFrame) -> pd.Series:
    """The area label of every row.

    `observed_event` carries `area_label`; `coverage` does not (spec §3's
    coverage column list), so it is re-derived from the layer name with the
    same grammar that produced the observed one. Deriving it here rather than
    matching coverage on the interval alone is what keeps one area's footprint
    from masking another's.
    """
    if "area_label" in frame:
        return frame["area_label"]
    return frame["layer_name"].map(lambda name: grammar.parse(str(name)).area)


def _prepare(frame: gpd.GeoDataFrame, *, code: str, table: str) -> gpd.GeoDataFrame:
    """Silver rows to gold's grain: valid geometry, an acquisition interval,
    an area label, and no undated rows.

    `acq_precision = "none"` is silver's record that a layer carried no date
    anywhere; such a row cannot be placed on any interval, so it is excluded
    (spec §3). A precision outside the vocabulary means silver changed under
    us and is raised rather than guessed at, and so is a row that claims a
    date precision but carries no date.
    """
    out = frame.copy()
    if not len(out):
        out["acq_start"] = pd.to_datetime(pd.Series([], dtype="object"))
        out["acq_end"] = out["acq_start"]
        out["area_label"] = pd.Series([], dtype="object")
        return out

    unknown = sorted(set(out["acq_precision"].dropna().unique()) - set(ACQ_PRECISIONS))
    if unknown or out["acq_precision"].isna().any():
        raise ValueError(
            f"{code}/{table}: acq_precision outside the vocabulary {ACQ_PRECISIONS}: "
            f"{unknown or ['<null>']}"
        )
    out["area_label"] = _area_labels(out)
    for col, window in (("acq_start", "acq_window_start"), ("acq_end", "acq_window_end")):
        out[col] = pd.to_datetime(out[window]).fillna(pd.to_datetime(out["acq_datetime"]))
    out = out[out["acq_precision"] != "none"].copy()
    undated = out["acq_start"].isna() | out["acq_end"].isna()
    if undated.any():
        raise ValueError(
            f"{code}/{table}: {int(undated.sum())} rows claim acq_precision "
            f"{sorted(out.loc[undated, 'acq_precision'].unique())} but have no acquisition date; "
            f"layers: {sorted(out.loc[undated, 'layer_name'].unique())[:5]}"
        )
    # UNOSAT shapefiles carry self-intersecting rings that crash GEOS unions;
    # make_valid is a no-op on already-valid geometry.
    out["geometry"] = out.geometry.make_valid()
    return out


# --- one label set ---------------------------------------------------------


def _union(frame: gpd.GeoDataFrame, kinds: tuple[str, ...]):
    sub = frame[frame["layer_kind"].isin(kinds)]
    return sub.geometry.union_all() if len(sub) else None


def _separates_flood(group: pd.DataFrame) -> bool:
    """True when some layer in the group set out to map flood extent.

    Then "no flood rows" means the source looked and found none (an empty
    geometry, area 0), not that flood is inseparable here (null).
    """
    return any(grammar.parse(str(name)).kind == "flood" for name in group["layer_name"].unique())


def _valid_mask(cov: gpd.GeoDataFrame, aoi, start, end):
    """The footprint for this (area, interval) minus what was not analysed."""
    same = cov[
        (cov["area_label"] == aoi) & (cov["acq_start"] == start) & (cov["acq_end"] == end)
    ]
    footprint = same[same["role"] == "footprint"]
    if not len(footprint):
        # `not_analysed` alone says what was NOT looked at, which is no
        # evidence at all about what was.
        return None, "none"
    valid = footprint.geometry.union_all()
    masked = same[same["role"] == "not_analysed"]
    if not len(masked):
        return valid, "footprint"
    return valid.difference(masked.geometry.union_all()), "footprint_minus_cloud"


def _values(series: pd.Series) -> list[str]:
    return [str(v) for v in series if v is not None and not _is_missing(v)]


def _is_missing(value) -> bool:
    missing = pd.isna(value)
    return bool(missing) if np.isscalar(missing) or isinstance(missing, bool) else False


def _most_common(series: pd.Series) -> str | None:
    """The modal value, ties broken alphabetically so a rebuild is stable."""
    counts = Counter(_values(series))
    if not counts:
        return None
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _joined(series: pd.Series) -> str | None:
    distinct = sorted(set(_values(series)))
    return "; ".join(distinct) if distinct else None


def _target_ids(series: pd.Series) -> str | None:
    ids: set[str] = set()
    for value in series:
        if value is None or isinstance(value, float):
            continue
        ids.update(str(t) for t in value)
    return "; ".join(sorted(ids)) if ids else None


def _label_set(code: str, aoi, start, end, group: gpd.GeoDataFrame, cov, meta: dict) -> dict:
    contributing = group[~group["layer_kind"].isin(EXCLUDED_KINDS)]
    flood = _union(contributing, FLOOD_KINDS)
    if flood is None and _separates_flood(group):
        flood = MultiPolygon()
    valid, basis = _valid_mask(cov, aoi, start, end)
    same_day = start.date() == end.date()
    sensor = _most_common(group["sensor"])
    return {
        "label_source": LABEL_SOURCE,
        "code": code,
        "name": meta.get("name"),
        "countries": meta.get("countries"),
        "aoi": aoi,
        "acq_start": start,
        "acq_end": end,
        "width_days": round((end - start).total_seconds() / 86400, 3),
        "label_day": str(start.date()) if same_day else None,
        "acq_method": _most_common(group["acq_method"]),
        "acq_precision": _most_common(group["acq_precision"]),
        # A conflict on any row is a conflict for the set: a consumer filtering
        # conflicts out must not keep a set that contains one.
        "acq_conflict": bool(group["acq_conflict"].fillna(False).any()),
        "sensor": sensor,
        "sensor_class": classes.sensor_class(sensor),
        "sensor_gsd": None,  # CEMS-only; UNOSAT publishes no ground sample distance
        "det_methods": None,  # CEMS-only
        # What the geometries are made of. The excluded kinds are reported by
        # `excluded_aggregate_n` instead, so this never implies they are in.
        "product_classes": _joined(contributing["layer_kind"]),
        "confidence": _joined(contributing["confidence"]),
        "water_status": _joined(contributing["water_status"]),
        "n_polygons": len(contributing),
        "valid_basis": basis,
        "target_ids": _target_ids(group["target_ids"]),
        "excluded_aggregate_n": int(len(group) - len(contributing)),
        "geom_water": _union(contributing, WATER_KINDS),
        "geom_flood": flood,
        "geom_possible": _union(contributing, POSSIBLE_KINDS),
        "geom_valid": valid,
    }


# --- the two frames --------------------------------------------------------


def _labels_frame(rows: list[dict]) -> gpd.GeoDataFrame:
    frame = pd.DataFrame(rows, columns=LABEL_COLUMNS)
    for col in ("acq_start", "acq_end"):
        frame[col] = pd.to_datetime(frame[col])
    for col in GEOMETRY_COLUMNS:
        frame[col] = gpd.GeoSeries(frame[col].tolist(), crs=WGS84, index=frame.index)
    return gpd.GeoDataFrame(frame, geometry="geom_water", crs=WGS84)


def _index_frame(rows: list[dict], labels: gpd.GeoDataFrame) -> pd.DataFrame:
    """The index, with the geometry-derived columns filled from ``labels``.

    ``labels`` was built from the same ``rows`` in the same order, so the two
    line up row for row; the areas and bounds are computed column-wise there
    (one reprojection each) rather than per label set.
    """
    index = pd.DataFrame(rows, columns=INDEX_COLUMNS)
    for col, geom in _AREA_OF.items():
        index[col] = (labels[geom].to_crs(EQ_AREA).area / 1e6).round(4).to_numpy()
    # Bounds describe the label's extent; `geom_water` is the widest of the
    # three (flood is part of it), so it is the source unless the set has only
    # possible-flood polygons.
    water, possible = labels["geom_water"], labels["geom_possible"]
    extent = gpd.GeoSeries(
        np.where(water.isna(), possible.to_numpy(), water.to_numpy()),
        crs=WGS84,
        index=labels.index,
    )
    bounds = extent.bounds
    for col in ("minx", "miny", "maxx", "maxy"):
        index[col] = bounds[col].to_numpy()
    for col in ("acq_start", "acq_end"):
        index[col] = pd.to_datetime(index[col])
    return index


def build_code(
    code: str,
    observed: gpd.GeoDataFrame,
    coverage: gpd.GeoDataFrame,
    meta: dict,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """One code's silver rows dissolved into label sets.

    Returns `(labels, index)`: the multi-geometry GeoParquet payload and the
    geometry-free index row per label set. Grouping is by `(area_label,
    acq_start, acq_end)` — the acquisition interval, so two passes over the
    same area on the same day stay one label set and two dates stay two.
    A code with no datable water polygons yields two empty frames with the
    full schema, which is a real state (zero rows), not a failure.
    """
    obs = _prepare(observed, code=code, table="observed_event")
    cov = _prepare(coverage, code=code, table="coverage")
    rows = [
        _label_set(code, aoi, start, end, group, cov, meta)
        for (aoi, start, end), group in obs.groupby(
            ["area_label", "acq_start", "acq_end"], dropna=False, sort=True
        )
    ]
    labels = _labels_frame(rows)
    return labels, _index_frame(rows, labels)


def code_meta(ledger: pd.DataFrame) -> dict[str, dict]:
    """`{event_code: {name, countries}}` from the resource ledger — the only
    place the archive records what an event code is called and where it is."""
    out: dict[str, dict] = {}
    for code, group in ledger.dropna(subset=["event_code"]).groupby("event_code"):
        out[str(code)] = {
            "name": _most_common(group["dataset_name"]),
            "countries": _joined(group["iso3"]),
        }
    return out


# --- paths and files -------------------------------------------------------

INDEX_PATH = f"{common.GOLD}/label_index.parquet"


def labels_path(code: str) -> str:
    return f"{common.GOLD}/labels/code={code}/data.parquet"


def index_part_path(code: str) -> str:
    """One index file per code, concatenated into `label_index.parquet` at the
    end of a run. The parts are what make the CLI resumable per code: a run
    that rebuilt three codes still publishes an index covering every code."""
    return f"{common.GOLD}/_index_parts/code={code}.parquet"


def local_mirror(work_dir) -> Path:
    return Path(work_dir) / "gold"


def local_path(work_dir, blob_path: str) -> Path:
    """Where a gold blob object is mirrored locally — the same relative layout
    below the root, as silver's mirror is."""
    return local_mirror(work_dir) / blob_path.split(f"{common.GOLD}/", 1)[1]


def read_labels_file(path: Path) -> gpd.GeoDataFrame:
    """Read one gold labels file, all four geometry columns intact.

    As with silver's layer files, partition inference has to be off: the file
    sits under a `code={EventCode}/` directory and carries a `code` column, and
    pyarrow refuses to merge the two.
    """
    return gpd.read_parquet(path, partitioning=None)


def read_partition(work_dir, store: BlobStore, table: str, code: str) -> gpd.GeoDataFrame:
    """Every silver layer file of one partition, concatenated.

    Blob decides what the partition holds (`silver.iter_layer_files`); the
    local mirror is only a cache of it.
    """
    frames = [
        silver.read_layer_file(path)
        for path in silver.iter_layer_files(work_dir, store, table, code)
    ]
    columns = silver.OBSERVED_COLUMNS if table == "observed_event" else silver.COVERAGE_COLUMNS
    if not frames:
        empty = pd.DataFrame(columns=columns)
        empty["geometry"] = gpd.GeoSeries([], crs=WGS84)
        return gpd.GeoDataFrame(empty, geometry="geometry", crs=WGS84)
    return gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs=WGS84
    )


def _codes_under(store: BlobStore, prefix: str) -> set[str]:
    return {
        path.split("code=", 1)[1].split("/", 1)[0].removesuffix(".parquet")
        for path in store.list_sizes(prefix)
        if "code=" in path
    }


def list_silver_codes(store: BlobStore) -> list[str]:
    """Codes with an `observed_event` partition in blob — gold's work list."""
    return sorted(_codes_under(store, f"{common.SILVER}/observed_event/code="))


def built_codes(store: BlobStore) -> set[str]:
    """Codes whose gold is already complete in blob. Both files must be there:
    a labels file with no index part would be invisible to the index, and an
    index part with no labels file would promise geometry that is not there."""
    return _codes_under(store, f"{common.GOLD}/labels/code=") & _codes_under(
        store, f"{common.GOLD}/_index_parts/code="
    )


def iter_index_parts(work_dir, store: BlobStore):
    """Every index part in blob, as local paths, mirroring as it goes — the
    same contract as `silver.iter_layer_files`: the listing decides."""
    local_dir = local_mirror(work_dir) / "_index_parts"
    for blob_path in sorted(store.list_sizes(f"{common.GOLD}/_index_parts/code=")):
        dest = local_path(work_dir, blob_path)
        if not dest.exists():
            local_dir.mkdir(parents=True, exist_ok=True)
            common.atomic_write(dest, store.download(blob_path))
        yield dest


def concat_index(paths) -> pd.DataFrame:
    """The whole label index from its parts, in a stable order."""
    frames = [pd.read_parquet(path) for path in paths]
    index = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=INDEX_COLUMNS)
    )
    index = index.reindex(columns=INDEX_COLUMNS)
    for col in ("acq_start", "acq_end"):
        index[col] = pd.to_datetime(index[col])
    return index.sort_values(["code", "aoi", "acq_start"]).reset_index(drop=True)
