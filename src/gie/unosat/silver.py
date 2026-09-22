"""Silver builder for the UNOSAT flood archive (spec §3, `silver.py`).

Composes the five pure modules built before it — `grammar` (layer names),
`classes` (per-polygon water class, sensor class), `readers` (GDAL reads,
WGS84, content hash) and `acquisition` (filename vs attribute dates) — into
one function, `build_layer`, that turns one archived layer into normalised
polygon rows plus the processing-ledger record describing what happened to
it. No I/O beyond the blob write helper at the bottom: the CLI
(`pipelines/unosat/silver.py`) owns downloads, extraction and checkpointing.

**Unit of work** is one distinct layer *content under its name*: `(code,
content_hash, layer_name)`. Silver stores one GeoParquet file per such unit
under its event-code partition (`silver_layer_path`), so a layer re-shipped
identically in 35 HDX zips is written once and every later encounter is a
cheap path-exists skip. The layer name is part of the file key because two
differently-named layers legitimately carry identical geometry (the same
analysis footprint under two acquisition dates); keying on content alone
silently dropped the second.

**Three states, never conflated** (global constraints): a layer we chose not
to ingest (`skipped_non_water`), one we could not classify (`unclassified`)
and one with no date anywhere (`no_date`) are each a recorded processing
status, not a silent drop; a layer with zero polygons is `ok` with zero rows.
Only the CLI adds `unreadable`, for a GDAL failure on one layer.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from datetime import UTC, datetime

import geopandas as gpd
import pandas as pd

from gie.unosat import acquisition, classes, common, grammar, readers
from gie.unosat.store import BlobStore

__all__ = [
    "OBSERVED_COLUMNS",
    "COVERAGE_COLUMNS",
    "SOURCES_COLUMNS",
    "PROCESSING_COLUMNS",
    "build_layer",
    "prescreen",
    "acq_status",
    "select_units",
    "layer_mismatch",
    "sibling_check",
    "layer_acquisitions",
    "load_processing",
    "merge_processing",
    "source_rows",
    "sources_frame",
    "processing_row",
    "processing_frame",
    "layer_file_key",
    "silver_layer_path",
    "write_layer",
    "is_polygon_type",
    "sensor_for",
]

# Spec §3 "Canonical columns on observed_event", plus the three provenance
# columns the brief adds (`content_hash`, `sha256`, `target_ids`): the file
# path is keyed by content hash, so a row must be able to name the content and
# the bronze objects it came from without a join back through the ledger.
OBSERVED_COLUMNS = [
    "code",
    "code_method",
    "event_code_attr",
    "target_ids",
    "layer_name",
    "layer_kind",
    "class_text",
    "class_method",
    "class_conflict",
    "area_label",
    "sensor",
    "sensor_method",
    "sensor_raw",
    "acq_datetime",
    "acq_window_start",
    "acq_window_end",
    "acq_precision",
    "acq_method",
    "acq_conflict",
    "water_status",
    "confidence",
    "field_validation",
    "staff_id",
    "notes",
    "geometry_source",
    "source_crs",
    "attrs_json",
    "content_hash",
    "sha256",
    "geometry",
]

# Spec §3's coverage list (`code`, `layer_name`, `role`, `sensor`, `acq_*`,
# `attrs_json`, `geometry`) plus the same provenance trio, `sensor_method`, and
# the `geometry_source`/`source_crs` pair the spec requires "on every row".
COVERAGE_COLUMNS = [
    "code",
    "target_ids",
    "layer_name",
    "role",
    "sensor",
    "sensor_method",
    "acq_datetime",
    "acq_window_start",
    "acq_window_end",
    "acq_precision",
    "acq_method",
    "acq_conflict",
    "geometry_source",
    "source_crs",
    "attrs_json",
    "content_hash",
    "sha256",
    "geometry",
]

# Spec §3: "one row per distinct (code, sensor, acq_datetime)". The window
# columns join that key because `acq_datetime` is null for every
# window-precision layer, which would otherwise collapse all of a code's
# composites into a single null-dated row per sensor.
SOURCES_COLUMNS = [
    "code",
    "sensor",
    "sensor_method",
    "acq_datetime",
    "acq_window_start",
    "acq_window_end",
    "acq_precision",
    "n_layers",
]

# One row per (sha256, layer) — the unit the CLI resumes on. `kind_counts_json`
# is spec §3's "polygon counts by layer_kind", carried as a JSON object string
# rather than a struct: the key set differs per layer, and a struct column
# would otherwise widen to the union of every kind with nulls everywhere else.
PROCESSING_COLUMNS = [
    "sha256",
    "layer",
    "code",
    "code_method",
    "codes_listed",
    "status",
    "table",
    "geometry_source",
    "content_hash",
    "target_ids",
    "n_polygons",
    "kind_counts_json",
    "shp_gdb_mismatch",
    "sibling_status",
    "source_crs",
    "reused",
    "error",
    "processed_at",
]

STATUSES = ("ok", "unclassified", "skipped_non_water", "no_date", "unreadable")
SENSOR_METHODS = ("filename", "attribute", "none")

# Layer-inventory statuses that mean a dataset's shapefile sibling could not be
# listed at all, so the GDB/SHP layer-name cross-check was never performed
# (recorded as `shp_gdb_mismatch = None`, not as an empty "they agree" list).
UNCOMPARABLE_SIBLING_STATUSES = frozenset(
    {"zip_unreadable", "gdb_unreadable", "missing_from_inventory"}
)

# One content listed under two event codes: UNOSAT shipped the same zip under
# two HDX resource names whose ISO3 disagrees. The rule is one silver partition
# per content, so a code must be chosen; the default is the most recently
# listed resource version, and these entries override that where we have
# checked which code is right.
#
# 09ab92a1…: listed as both FL20250812CPV and FL20250812COD. Both datasets are
# Cabo Verde and the per-polygon EventCode attribute says COD, so COD is the
# typo inside the product; the CPV listing is also the newer of the two, but
# it is pinned here rather than left to the timestamp.
CODE_OVERRIDES: dict[str, str] = {
    "09ab92a146c0cf431ddb84241db45ecbb6de03f5718c5c52b52c44757c616a07": "FL20250812CPV",
}
# How `code` was obtained. Only `resource_name` is produced today: silver
# processes flood/cyclone resources, and that scope is itself derived from a
# parseable event code in the resource name (`common.parse_event_code` ->
# `common.scope_for`), so the spec's attribute/dataset-name fallbacks are
# unreachable for this selection. The CLI raises rather than guessing if a
# selected row ever turns up without one.
CODE_METHODS = ("resource_name", "attribute", "dataset_name")

# The processing ledger's file name. Deliberately the same locally and in blob
# (`{SILVER_META}/processing.parquet`) so `meta.bootstrap_work_dir` can restore
# it by name like every other `_meta` table.
PROCESSING_FILE = "processing.parquet"

# Attribute names differ between the geodatabase exports and the shapefile
# exports (DBF truncates field names to 10 characters), and across eras. Each
# logical field is resolved by trying its aliases in order against the layer's
# own columns.
ATTR_ALIASES: dict[str, tuple[str, ...]] = {
    "class": ("Water_Class", "Water_Class2", "Water_Class_1", "Water_Clas"),
    "sensor": ("Sensor_ID", "SensorID", "Sensor_I"),
    "confidence": ("Confidence_ID", "Confidence", "Confidenc"),
    "field_validation": ("Field_Validation", "Field_Vali"),
    "water_status": ("Water_StatusID", "WaterStatus", "Water_Stat"),
    "notes": ("Notes",),
    "staff_id": ("StaffID", "Staff_ID"),
    "event_code_attr": ("EventCode", "Event_Code", "EventCod"),
}
# The per-polygon acquisition date: `Sensor_Date` in a GDB, truncated to
# `Sensor_Dat` in a shapefile, `SensorDate` on the coverage layers.
SENSOR_DATE_ALIASES = ("Sensor_Date", "Sensor_Dat", "SensorDate")


def is_polygon_type(geometry_type: str | None) -> bool | None:
    """Whether an inventory ``geometry_type`` names a polygonal layer.

    ``None`` (the inventory records no geometry type for shapefile members)
    means *unknown*, not *not polygonal*: the caller must read the layer and
    let `build_layer` decide. Kept deliberately loose about the exact spelling
    so "Polygon", "MultiPolygon" and "3D Polygon" all match.
    """
    if geometry_type is None:
        return None
    return "polygon" in geometry_type.casefold()


def prescreen(ln: grammar.LayerName, geometry_type: str | None) -> str | None:
    """The processing status decidable before the layer is read, or ``None``
    when it must be read to be decided.

    The CLI uses this to avoid GDAL reads it will throw away (roughly a
    quarter of the inventory is impact/admin or non-polygonal); `build_layer`
    uses the same function so the rule has exactly one definition.
    """
    if ln.kind == "skip":
        return "skipped_non_water"
    if ln.kind is None:
        return "unclassified"
    if is_polygon_type(geometry_type) is False:
        return "skipped_non_water"
    return None


def acq_status(acqs: list[dict]) -> str:
    """`no_date` when a layer resolved no date at all, else `ok`. A layer with
    no polygons has no acquisitions and is `ok` (spec §3: absence of polygons
    is a result, not an error)."""
    if acqs and all(a["acq_precision"] == "none" for a in acqs):
        return "no_date"
    return "ok"


def layer_mismatch(gdb_layers: set[str], shp_layers: set[str]) -> list[str]:
    """Layer names present in one of a dataset's two exports but not the
    other, sorted. Empty is the expected result and is recorded as such — an
    empty list means "checked, they agree", not "not checked"."""
    return sorted(set(gdb_layers) ^ set(shp_layers))


def sibling_check(
    layers_df: pd.DataFrame,
    status_df: pd.DataFrame,
    sha256: str,
    siblings: list[str],
) -> tuple[list[str] | None, str | None]:
    """``(shp_gdb_mismatch, sibling_status)`` for one GDB content.

    The cross-check needs the sibling shapefile zip's layer inventory. When
    that zip could not be inventoried at all (`zip_unreadable`,
    `gdb_unreadable`, `missing_from_inventory`, or no status row), the check
    did not happen: the mismatch is ``None`` and `sibling_status` says why.
    Returning an empty list there would claim the two exports agree when they
    were never compared. A sibling that *was* inventoried gives a real list
    (possibly empty) and `sibling_status = "ok"`.

    ``(None, None)`` means there is no shapefile sibling to compare against.
    """
    if not siblings:
        return None, None
    inventoried = [s for s in siblings if (layers_df["sha256"] == s).any()]
    if not inventoried:
        statuses = status_df.loc[status_df["sha256"].isin(siblings), "status"]
        blocked = sorted({s for s in statuses if s in UNCOMPARABLE_SIBLING_STATUSES})
        return None, (blocked[0] if blocked else "absent")
    shp_layers = set(layers_df.loc[layers_df["sha256"].isin(inventoried), "layer"])
    gdb_layers = set(layers_df.loc[layers_df["sha256"] == sha256, "layer"])
    return layer_mismatch(gdb_layers, shp_layers), "ok"


def _codes_for(rows: pd.DataFrame) -> tuple[str | None, list[str]]:
    """``(chosen code, every code this content was listed under)`` for one
    sha256's ledger rows.

    The choice is `CODE_OVERRIDES` first, then the code of the most recently
    listed resource version (`last_modified`; rows without one sort first, so
    a dated listing always beats an undated one). Ties fall back to the
    resource name, so the result never depends on row order.
    """
    listed = sorted({c for c in rows["event_code"].dropna().unique()})
    sha = rows["sha256"].iloc[0]
    if sha in CODE_OVERRIDES:
        return CODE_OVERRIDES[sha], listed
    if len(listed) <= 1:
        return (listed[0] if listed else None), listed
    order = rows.assign(_lm=pd.to_datetime(rows.get("last_modified"), errors="coerce", utc=True))
    order = order.sort_values(["_lm", "resource_name"], na_position="first")
    return order["event_code"].iloc[-1], listed


def select_units(ledger: pd.DataFrame) -> list[dict]:
    """The zips silver reads, one per distinct bronze content, GDB-first.

    Per dataset: if any uploaded Geodatabase resource exists, its zips are the
    geometry source and the dataset's SHP zips are used only to cross-check
    layer names (`layer_mismatch`); a dataset with no GDB falls back to its
    SHP zips. Only flood/cyclone scope, only uploaded resources.

    Units are keyed by sha256 because bronze is content-addressed: the same
    zip shipped under several datasets is read once, carrying every
    `target_id` that delivered it.

    One content occasionally appears under two event codes (an ISO3 typo in
    one of UNOSAT's HDX resource names). One partition per content is the
    rule, so a code is chosen — from `CODE_OVERRIDES` where we have checked
    which one is right, otherwise from the most recently listed resource
    version — and *every* listed code is carried on the unit as `codes_listed`
    and onto its processing rows, so the choice is visible rather than
    implicit.
    """
    up = ledger[
        (ledger["scope"] == "flood")
        & ledger["status"].isin(common.UPLOADED_STATUSES)
        & ledger["format"].isin(("Geodatabase", "SHP"))
        & ledger["sha256"].notna()
    ]
    targets = up.groupby("sha256")["target_id"].apply(lambda s: sorted(s.dropna().unique()))
    codes = {sha: _codes_for(grp) for sha, grp in up.groupby("sha256")}

    chosen: dict[str, dict] = {}
    for _, rows in up.groupby("dataset_id"):
        gdbs = rows[rows["format"] == "Geodatabase"]
        source_rows_, source = (gdbs, "gdb") if len(gdbs) else (rows, "shp")
        siblings = sorted(rows.loc[rows["format"] == "SHP", "sha256"].dropna().unique())
        for r in source_rows_.drop_duplicates("sha256").itertuples():
            code, codes_listed = codes[r.sha256]
            unit = chosen.setdefault(
                r.sha256,
                {
                    "sha256": r.sha256,
                    "resource_name": r.resource_name,
                    "geometry_source": source,
                    "code": code,
                    "code_method": "resource_name",
                    "codes_listed": codes_listed,
                    "target_ids": list(targets.loc[r.sha256]),
                    "sibling_shp_sha256s": [],
                },
            )
            if source == "gdb":
                unit["sibling_shp_sha256s"] = sorted(
                    set(unit["sibling_shp_sha256s"]) | set(siblings)
                )

    missing = sorted(
        u["sha256"] for u in chosen.values() if pd.isna(u["code"]) or not u["code"]
    )
    if missing:
        raise ValueError(
            f"{len(missing)} flood/cyclone contents have no event code in the ledger "
            f"(first: {missing[0]}); silver cannot choose a partition key"
        )
    return sorted(chosen.values(), key=lambda u: (u["code"], u["resource_name"], u["sha256"]))


def load_processing(work_dir) -> pd.DataFrame:
    """The accumulated processing ledger under ``work_dir``; a typed empty
    frame before the first run."""
    path = work_dir / PROCESSING_FILE
    if path.exists():
        return pd.read_parquet(path).reindex(columns=PROCESSING_COLUMNS)
    return pd.DataFrame(columns=PROCESSING_COLUMNS)


def merge_processing(proc_df: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Fold one batch into the processing ledger: rows for a ``(sha256,
    layer)`` already present are replaced, not appended to. Pure."""
    new = processing_frame(new_rows)
    if proc_df.empty:
        return new
    if new.empty:
        return proc_df[PROCESSING_COLUMNS]
    old_idx = pd.MultiIndex.from_frame(proc_df[["sha256", "layer"]])
    new_idx = pd.MultiIndex.from_frame(new[["sha256", "layer"]])
    kept = proc_df[~old_idx.isin(new_idx)]
    return pd.concat([kept, new], ignore_index=True)[PROCESSING_COLUMNS]


def _first_present(gdf: gpd.GeoDataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in gdf.columns:
            return name
    return None


def _decoded_col(gdf: gpd.GeoDataFrame, field: str | None) -> str | None:
    """The optional ``d_*`` column some shapefile exports ship alongside a
    coded field, carrying the domain text the shapefile itself cannot hold.
    Tries the full name and the 10-character DBF truncation
    (``d_Water_Class`` -> ``d_Water_Cl``)."""
    if field is None:
        return None
    full = f"d_{field}"
    return _first_present(gdf, (full, full[:10]))


def _text(value: object) -> str | None:
    """A raw attribute value as display text, with every missing marker and
    the empty string collapsed to ``None``."""
    scalar = readers.json_scalar(value)
    if scalar is None:
        return None
    text = str(scalar).strip()
    return text or None


def _bind(gdf: gpd.GeoDataFrame, domain_lookup: dict[str, dict[str, str]] | None) -> dict:
    """Resolve every logical attribute once per layer: which column holds it,
    which coded-value domain is bound to that column, and whether a decoded
    ``d_*`` companion column is present."""
    bound = {}
    for logical, aliases in ATTR_ALIASES.items():
        col = _first_present(gdf, aliases)
        lookup = domain_lookup.get(col) if (domain_lookup and col) else None
        bound[logical] = (col, lookup, _decoded_col(gdf, col))
    return bound


def _raw(row: pd.Series, bound: tuple) -> object:
    col = bound[0]
    return readers.json_scalar(row[col]) if col is not None else None


def _decoded(row: pd.Series, bound: tuple) -> str | None:
    col = bound[2]
    return _text(row[col]) if col is not None else None


def _attr_value(raw: object, decoded: str | None, lookup: dict[str, str] | None) -> str | None:
    """One non-class coded attribute as text: the decoded column when present,
    else the domain value for the code, else the raw value verbatim.

    A code that its bound domain does not contain resolves to ``None`` — the
    same refusal to guess `classes.resolve_class` makes for `Water_Class`
    (spec §3: "Confidence 0 is not in the Confidence domain"). The raw code is
    never lost: it is in `attrs_json` verbatim.
    """
    if decoded is not None:
        return decoded
    if raw is None:
        return None
    if lookup is not None:
        key = classes.code_key(raw)
        return lookup.get(key) if key is not None else None
    return _text(raw)


def _attr_text(row: pd.Series, bound: tuple) -> str | None:
    return _attr_value(_raw(row, bound), _decoded(row, bound), bound[1])


def _attr_column(frame: pd.DataFrame, bound: tuple) -> list[str | None]:
    """`_attr_text` over a whole frame, column-wise. Used where only the set of
    distinct values matters (the `sources` table), so a second `iterrows` pass
    over every polygon is not needed."""
    col, lookup, dcol = bound
    n = len(frame)
    raws = [readers.json_scalar(v) for v in frame[col]] if col is not None else [None] * n
    decs = [_text(v) for v in frame[dcol]] if dcol is not None else [None] * n
    return [_attr_value(r, d, lookup) for r, d in zip(raws, decs, strict=True)]


def sensor_for(ln: grammar.LayerName, attr_sensor: str | None) -> tuple[str | None, str]:
    """``(sensor, sensor_method)`` for one polygon.

    The layer name is authoritative when it names a sensor. Otherwise the
    per-polygon `Sensor_ID` text is used, which carries sensors the filename
    grammar never sees (COSMO-SkyMed, SkySat, SPOT, Kompsat — see
    `classes.sensor_class`); `sensor_method` says which of the two it was, so
    a consumer never has to guess whether a sensor came from the file name.
    """
    if ln.sensor is not None:
        return ln.sensor, "filename"
    if attr_sensor is not None:
        return attr_sensor, "attribute"
    return None, "none"


def _class_text(method: str, raw: object, lookup: dict[str, str] | None, decoded: str | None):
    """The resolved water-class text for the path `classes.resolve_class` took.

    Derived from the returned `class_method` rather than by re-walking the
    precedence, so the text can never describe a different path than the one
    actually taken.
    """
    if method == "decoded_column":
        return decoded
    if method == "domain":
        key = classes.code_key(raw)
        return lookup.get(key) if (lookup is not None and key is not None) else None
    if method == "text":
        return _text(raw)
    return None


def layer_acquisitions(
    ln: grammar.LayerName, gdf: gpd.GeoDataFrame
) -> list[tuple[dict, gpd.GeoDataFrame]]:
    """Split one layer into (acquisition, polygons) groups, one per distinct
    per-polygon sensor date.

    `acquisition.resolve_acq` raises if handed more than one distinct date, by
    design: reconciling the filename against several attribute dates at once
    would mean inventing a single answer for a layer that genuinely carries
    several acquisitions. So the split happens here first, and each group is
    resolved on its own. Polygons with a null sensor date form their own group
    (their acquisition then rests on the filename alone), ordered last.

    A layer with no sensor-date column at all is one group resolved from the
    filename. An empty layer has no groups — there is nothing to acquire.
    """
    if len(gdf) == 0:
        return []
    col = _first_present(gdf, SENSOR_DATE_ALIASES)
    if col is None:
        empty = pd.Series([], dtype="object")
        return [(acquisition.resolve_acq(ln, empty), gdf)]

    dates = gdf[col].map(acquisition.normalise_date)
    groups: list[tuple[dict, gpd.GeoDataFrame]] = []
    for value in sorted({d for d in dates if d is not None}):
        mask = dates == value
        groups.append((acquisition.resolve_acq(ln, gdf.loc[mask, col]), gdf[mask]))
    null_mask = dates.isna()
    if null_mask.any():
        groups.append((acquisition.resolve_acq(ln, gdf.loc[null_mask, col]), gdf[null_mask]))
    return groups


def _observed_row(row: pd.Series, ln: grammar.LayerName, bound: dict, base: dict) -> dict:
    raw_class = _raw(row, bound["class"])
    decoded_class = _decoded(row, bound["class"])
    lookup = bound["class"][1]
    polygon_kind, method = classes.resolve_class(
        raw_class, domain_lookup=lookup, decoded_text=decoded_class
    )
    unfilled = classes.is_unfilled(
        {
            "class": raw_class,
            "sensor": _raw(row, bound["sensor"]),
            "confidence": _raw(row, bound["confidence"]),
        }
    )
    kind, conflict = classes.final_kind(ln.kind, polygon_kind, unfilled)
    if polygon_kind is None or unfilled:
        # `final_kind` took the layer name's kind; say so. The layer is always
        # classifiable here (an unclassifiable one never reaches row building),
        # so `kind` is never null on a silver row and `class_method =
        # unresolved_code` is unreachable — the unresolved code itself stays
        # visible in `attrs_json`.
        method = "layer_name"
        class_text = None
    else:
        class_text = _class_text(method, raw_class, lookup, decoded_class)
    sensor, sensor_method = sensor_for(ln, _attr_text(row, bound["sensor"]))
    return base | {
        "event_code_attr": _attr_text(row, bound["event_code_attr"]),
        "layer_kind": kind,
        "class_text": class_text,
        "class_method": method,
        "class_conflict": conflict,
        "area_label": ln.area,
        "sensor": sensor,
        "sensor_method": sensor_method,
        "sensor_raw": ln.sensor_raw,
        "water_status": _attr_text(row, bound["water_status"]),
        "confidence": _attr_text(row, bound["confidence"]),
        "field_validation": _attr_text(row, bound["field_validation"]),
        "staff_id": _attr_text(row, bound["staff_id"]),
        "notes": _attr_text(row, bound["notes"]),
        "attrs_json": readers.attrs_json(row),
        "geometry": row.geometry,
    }


def _coverage_row(row: pd.Series, ln: grammar.LayerName, bound: dict, base: dict) -> dict:
    sensor, sensor_method = sensor_for(ln, _attr_text(row, bound["sensor"]))
    return base | {
        "role": ln.kind,
        "sensor": sensor,
        "sensor_method": sensor_method,
        "attrs_json": readers.attrs_json(row),
        "geometry": row.geometry,
    }


def _frame(rows: list[dict], columns: list[str]) -> gpd.GeoDataFrame:
    """Rows to a WGS84 GeoDataFrame with exactly ``columns``, in order.

    Dtypes are pinned rather than inferred because gold concatenates many of
    these files: an all-null object column would otherwise land in parquet as
    a null-typed column and refuse to concat with a timestamp one.
    """
    frame = gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns),
        geometry="geometry",
        crs="EPSG:4326",
    )
    for col in ("acq_datetime", "acq_window_start", "acq_window_end"):
        frame[col] = pd.to_datetime(frame[col], errors="raise")
    for col in ("class_conflict", "acq_conflict"):
        if col in frame:
            frame[col] = frame[col].astype(bool)
    return frame


def processing_row(
    *,
    sha256: str,
    layer: str,
    code: str,
    code_method: str,
    status: str,
    geometry_source: str,
    target_ids: list[str],
    codes_listed: list[str] | None = None,
    table: str | None = None,
    content_hash: str | None = None,
    n_polygons: int = 0,
    kind_counts: dict[str, int] | None = None,
    shp_gdb_mismatch: list[str] | None = None,
    sibling_status: str | None = None,
    source_crs: str | None = None,
    reused: bool = False,
    error: str | None = None,
) -> dict:
    """One processing-ledger record, with every column spelled once.

    ``shp_gdb_mismatch`` keeps the three states apart: a list (possibly empty)
    means the GDB/SHP layer-name cross-check ran, ``None`` means it could not
    (no shapefile sibling, or one that could not be inventoried —
    ``sibling_status`` then says which).
    """
    if status not in STATUSES:
        raise ValueError(f"unknown processing status {status!r}; expected one of {STATUSES}")
    return {
        "sha256": sha256,
        "layer": layer,
        "code": code,
        "code_method": code_method,
        "codes_listed": list(codes_listed) if codes_listed is not None else [code],
        "status": status,
        "table": table,
        "geometry_source": geometry_source,
        "content_hash": content_hash,
        "target_ids": list(target_ids),
        "n_polygons": n_polygons,
        "kind_counts_json": json.dumps(kind_counts or {}, sort_keys=True),
        "shp_gdb_mismatch": None if shp_gdb_mismatch is None else list(shp_gdb_mismatch),
        "sibling_status": sibling_status,
        "source_crs": source_crs,
        "reused": reused,
        "error": error,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def processing_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=PROCESSING_COLUMNS)


def build_layer(
    code: str,
    code_method: str,
    ln: grammar.LayerName,
    gdf: gpd.GeoDataFrame,
    *,
    source: str,
    sha256: str,
    target_ids: list[str],
    domain_lookup: dict[str, dict[str, str]] | None,
    content_hash: str | None = None,
    codes_listed: list[str] | None = None,
) -> tuple[gpd.GeoDataFrame | None, str | None, dict]:
    """One archived layer -> (rows, table, processing record).

    ``rows`` is ``None`` (with ``table`` ``None``) exactly when the layer
    produces no silver table: a non-water layer by name (`skipped_non_water`),
    a name the grammar cannot classify (`unclassified`), or a non-polygonal
    layer (`skipped_non_water` — points and lines are impact features, not
    water extents). Every other layer returns a frame, which may legitimately
    be empty (`ok`, zero rows: the layer genuinely has no polygons).

    ``domain_lookup`` maps a GDB field name to that field's coded-value domain
    for *this* layer (`{field: {code: value}}`, built from `domains.parquet`);
    ``None`` for a shapefile, whose class values are text already.

    ``content_hash`` may be passed in when the caller has already computed it
    (the CLI hashes first, to decide whether the output file already exists);
    it is computed here when it is not.

    A layer with no date anywhere keeps its rows and is recorded `no_date`:
    the rows carry ``acq_precision = "none"`` and gold excludes them on that,
    so the fact is visible rather than the polygons silently discarded.
    """
    base = {
        "sha256": sha256,
        "layer": ln.raw,
        "code": code,
        "code_method": code_method,
        "codes_listed": codes_listed,
        "geometry_source": source,
        "target_ids": list(target_ids),
        "n_polygons": len(gdf),
    }

    # Hashing is an iterrows pass over every polygon, so it happens only for a
    # layer that will actually produce a file.
    prescreened = prescreen(ln, None)
    if prescreened is not None:
        return None, None, processing_row(**base, status=prescreened)
    if len(gdf) and not gdf.geometry.geom_type.isin(("Polygon", "MultiPolygon")).all():
        return None, None, processing_row(**base, status="skipped_non_water")
    chash = readers.content_hash(gdf) if content_hash is None else content_hash

    if len(gdf):
        gdf, source_crs = readers.to_wgs84(gdf, ln.raw)
    else:
        # Nothing to reproject: an empty layer without a CRS is not a data
        # problem, so it must not raise the way a populated one does.
        source_crs = gdf.crs.to_string() if gdf.crs is not None else None

    table = ln.table
    columns = OBSERVED_COLUMNS if table == "observed_event" else COVERAGE_COLUMNS
    make_row = _observed_row if table == "observed_event" else _coverage_row
    bound = _bind(gdf, domain_lookup)
    shared = {
        "code": code,
        "code_method": code_method,
        "target_ids": list(target_ids),
        "layer_name": ln.raw,
        "geometry_source": source,
        "source_crs": source_crs,
        "content_hash": chash,
        "sha256": sha256,
    }

    groups = layer_acquisitions(ln, gdf)
    rows: list[dict] = []
    for acq, sub in groups:
        row_base = shared | acq
        rows.extend(make_row(row, ln, bound, row_base) for _, row in sub.iterrows())

    frame = _frame(rows, columns)
    counts = Counter(frame["layer_kind" if table == "observed_event" else "role"].dropna())
    record = processing_row(
        **base,
        status=acq_status([acq for acq, _ in groups]),
        table=table,
        content_hash=chash,
        source_crs=source_crs,
        kind_counts=dict(counts),
    )
    return frame, table, record


def source_rows(
    code: str,
    ln: grammar.LayerName,
    groups: list[tuple[dict, gpd.GeoDataFrame]],
    *,
    domain_lookup: dict[str, dict[str, str]] | None,
) -> list[dict]:
    """The `sources` rows one layer contributes: each acquisition the layer
    resolved to, crossed with the sensors its polygons were acquired by.

    The sensor is resolved through `sensor_for`, exactly as on the
    `observed_event`/`coverage` rows, so the two tables never disagree about
    which sensor an acquisition belongs to. Resolution is column-wise rather
    than row-wise: only the distinct values matter here.
    """
    rows = []
    for acq, sub in groups:
        if ln.sensor is not None:
            sensors = [sensor_for(ln, None)]
        else:
            bound = _bind(sub, domain_lookup)
            sensors = sorted(
                {sensor_for(ln, value) for value in _attr_column(sub, bound["sensor"])},
                key=lambda s: (s[0] is None, s[0] or ""),
            )
        for sensor, sensor_method in sensors:
            rows.append(
                {
                    "code": code,
                    "sensor": sensor,
                    "sensor_method": sensor_method,
                    "acq_datetime": acq["acq_datetime"],
                    "acq_window_start": acq["acq_window_start"],
                    "acq_window_end": acq["acq_window_end"],
                    "acq_precision": acq["acq_precision"],
                    "n_layers": 1,
                }
            )
    return rows


def sources_frame(rows: list[dict]) -> pd.DataFrame:
    """Collapse accumulated `source_rows` to one row per distinct
    ``(code, sensor, acquisition)``, counting the layers behind each."""
    frame = pd.DataFrame(rows, columns=SOURCES_COLUMNS)
    if frame.empty:
        return frame
    keys = [c for c in SOURCES_COLUMNS if c != "n_layers"]
    grouped = frame.groupby(keys, dropna=False, as_index=False)["n_layers"].sum()
    return grouped[SOURCES_COLUMNS]


def layer_file_key(content_hash: str, layer_name: str) -> str:
    """The file key for one layer: its content hash plus a short digest of its
    name.

    The name is part of the key because identical content under two different
    names is real and meaningful — the same analysis footprint shipped as
    `…_20190330_AnalysisExtent_…` and `…_20190402_AnalysisExtent_…` describes
    two acquisitions. Keying on content alone collapsed them onto one path and
    silently dropped the second as already-written.
    """
    return f"{content_hash}-{hashlib.sha256(layer_name.encode()).hexdigest()[:8]}"


def silver_layer_path(table: str, code: str, content_hash: str, layer_name: str) -> str:
    """One file per distinct (layer content, layer name) under its event-code
    partition."""
    return (
        f"{common.SILVER}/{table}/code={code}/"
        f"layer={layer_file_key(content_hash, layer_name)}.parquet"
    )


def sources_path(code: str) -> str:
    return f"{common.SILVER}/sources/code={code}/data.parquet"


def write_layer(store: BlobStore, path: str, frame: pd.DataFrame) -> int:
    """Serialise one layer's rows and upload them. Returns the bytes written."""
    buf = io.BytesIO()
    frame.to_parquet(buf, compression="zstd")
    data = buf.getvalue()
    store.upload(path, data)
    return len(data)
