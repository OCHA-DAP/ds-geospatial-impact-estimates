# UNOSAT Archive — Silver and Gold (labels) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the archived UNOSAT flood/cyclone zips (bronze, PR #128) into normalised per-polygon tables (silver) and then into label sets with separate water, flood and possible-flood geometries plus a valid-observation mask (gold v2), in the shape the flood-fusion label reader will consume alongside CEMS.

**Architecture:** Pure library modules in `src/gie/unosat/` — a layer inventory over every geodatabase and shapefile in bronze, a layer-name grammar, a per-polygon water-class resolver backed by the extracted domains, a layer reader (GDB first, SHP fallback), an acquisition-date resolver — composed by a silver builder that writes one GeoParquet file per distinct layer content under `silver/<table>/code=<EventCode>/`, and a gold builder that dissolves silver per acquisition into `gold/labels/code=<EventCode>/data.parquet` plus a single `gold/label_index.parquet`. Thin CLIs in `pipelines/unosat/`, resumable and checkpointed like the bronze stages, plus audit S/G rules.

**Tech Stack:** Python 3.13 via `uv`, pandas, geopandas ≥1.0 (multi-geometry GeoParquet), shapely 2, pyogrio (reads GDB via OpenFileGDB and SHP inside zips), pyarrow, `ogrinfo` CLI for domains/inventory, ocha-stratus + `gie.blobio` for blob, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md` §3 (silver), §4 (gold), §5 (S/G audit rules). Read it fully. Bronze facts this plan relies on come from the completed run (see `data_ledger.md` row `unosat | bronze`): 911 flood/cyclone datasets uploaded, 777 with a GDB, 133 SHP-only; three water-class domains (`Water_Class`, `Water_Class2`, `Water_Class_1`) fully enumerated in `_meta/domains.parquet`.

## Global Constraints

- Branch `feat/unosat-silver-gold` (worktree `../ds-geospatial-impact-estimates.worktrees/feat-unosat-silver-gold`), off `feat/unosat-archive` (PR #128). Commit per task; **no `Co-Authored-By` or AI attribution lines** (user rule).
- Run: `uv run --group etl --group api python pipelines/unosat/<stage>.py …`; tests `uv run --group etl pytest tests/unosat -q`; lint `uv run ruff check src/gie/unosat pipelines/unosat tests/unosat` (line length 100).
- Bronze is read-only input. Never write under `unosat/bronze/blob=`; silver/gold write under `unosat/silver/`, `unosat/gold/` in container `global`, stage `dev` unless `--stage prod`.
- Reuse the bronze machinery, do not re-implement: `common.add_common_args`, `meta.bootstrap`, `cache.read_through`, `common.atomic_write`, `store.DataLakeStore`, `domains.load_frames`, the ledger at `resources.parquet` (statuses in `common.UPLOADED_STATUSES` are the uploaded set).
- **Fail loudly.** Three states, never conflated: *upstream/content absence* (a layer with no polygons, a zip with no water layers, a name the grammar cannot classify, a code with no domain entry) → explicit processing-ledger status or column value; *our failure* (GDAL cannot read a layer, a write fails) → recorded status with error text where the run can continue, raise where it cannot; *empty* → `ok` with zero rows. No `try/except: continue`; catch only named exceptions.
- Vocabularies (exact strings): `layer_kind` ∈ {`water`, `water_pre`, `flood`, `flood_possible`, `other_water`, `aggregate_max`, `aggregate_min`}; coverage `role` ∈ {`footprint`, `not_analysed`}; `class_method` ∈ {`domain`, `text`, `decoded_column`, `layer_name`, `unresolved_code`}; `acq_precision` ∈ {`date`, `window`, `none`}; `acq_method` ∈ {`attribute`, `filename`, `window`, `none`}; `geometry_source` ∈ {`gdb`, `shp`}; processing `status` ∈ {`ok`, `unclassified`, `skipped_non_water`, `no_date`, `unreadable`}; `sensor_class` ∈ {`sar`, `optical_vhr`, `optical_hr`, `optical_coarse`, `multiple`, `unknown`}; `valid_basis` ∈ {`footprint_minus_cloud`, `footprint`, `none`}.
- Silver layout (deviation from spec §3's `code=…/data.parquet`, recorded in the spec by Task 6): `unosat/silver/{observed_event,coverage}/code={EventCode}/layer={content_hash}.parquet` — one file per distinct layer content, idempotent (exists → skip), so a layer re-shipped in 35 zips is stored once. `unosat/silver/sources/code={EventCode}/data.parquet` and `unosat/silver/_meta/{layers,processing}.parquet`.
- Gold layout: `unosat/gold/labels/code={EventCode}/data.parquet`, `unosat/gold/_index_parts/code={EventCode}.parquet`, `unosat/gold/label_index.parquet`.
- Never commit anything under the work dir or `data/`.

## File Structure

```
src/gie/unosat/layers.py        inventory: every layer in every flood zip (GDB feature classes via ogrinfo, SHP members)
src/gie/unosat/grammar.py       LayerName parsing: sensor, dates, kind, area
src/gie/unosat/classes.py       Water_Class resolution + layer_kind precedence + sensor_class
src/gie/unosat/readers.py       read one layer to a GeoDataFrame (GDB or SHP), reproject, attrs_json, content hash
src/gie/unosat/acquisition.py   acq_* columns from filename dates + per-polygon sensor date
src/gie/unosat/silver.py        build rows for one layer; write per-layer parquet; processing ledger
src/gie/unosat/gold.py          dissolve per (code, area, acq interval) → labels + index rows
src/gie/unosat/audit.py         add S1–S6, G1–G2 (bronze rules stay)
pipelines/unosat/layers.py      CLI
pipelines/unosat/silver.py      CLI (resumable, checkpointed)
pipelines/unosat/gold.py        CLI
pipelines/unosat/audit.py       gains --silver / --gold sections
tests/unosat/fixtures/layer_names_flood.txt   2,600 real SHP layer names (committed fixture)
tests/unosat/test_layers.py, test_grammar.py, test_classes.py, test_readers.py, test_acquisition.py, test_silver.py, test_gold.py, test_audit.py (extend)
docs/decisions/0034-flood-label-gold-v2-water-and-flood-geometries.md
```

---

### Task 1: Layer inventory over bronze

**Files:** Create `src/gie/unosat/layers.py`, `pipelines/unosat/layers.py`, `tests/unosat/test_layers.py`.

**Interfaces:**
- Consumes: ledger (`resources.parquet`), `zip_contents.parquet`, `domains.py.ogrinfo_json`, `cache.read_through`, `meta.bootstrap`.
- Produces: `layers_from_ogrinfo(sha256, zip_basename, info: dict) -> list[dict]` rows `{sha256, zip_basename, source ("gdb"), layer, geometry_type, feature_count, fields (list[str]), field_domains (dict field→domain_name)}`; `layers_from_zip_members(sha256, zip_basename, members: list[str]) -> list[dict]` (source `"shp"`, one row per `.shp`, geometry_type None, fields None); `LAYERS_COLUMNS`; CLI writes `silver/_meta/layers.parquet` (+ upload) and `silver/_meta/layers_status.parquet` (`sha256, status ∈ {ok, gdb_unreadable, zip_unreadable, no_layers}, error`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unosat/test_layers.py
from gie.unosat import layers

INFO = {"layers": [
    {"name": "VIIRS_20211119_20211123_FloodExtent_SouthSudan", "featureCount": 1,
     "geometryFields": [{"type": "MultiPolygon"}],
     "fields": [{"name": "Water_Class", "domainName": "Water_Class2"}, {"name": "Notes"}]},
    {"name": "Water_Class", "featureCount": 10, "geometryFields": [], "fields": [{"name": "Water_Class_code"}]},
]}

def test_layers_from_ogrinfo_keeps_geometry_layers_and_domain_bindings():
    rows = layers.layers_from_ogrinfo("s" * 64, "X_gdb.zip", INFO)
    assert [r["layer"] for r in rows] == ["VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Water_Class"]
    r = rows[0]
    assert r["source"] == "gdb" and r["geometry_type"] == "MultiPolygon" and r["feature_count"] == 1
    assert r["fields"] == ["Water_Class", "Notes"] and r["field_domains"] == {"Water_Class": "Water_Class2"}
    assert rows[1]["geometry_type"] is None  # a lookup table, no geometry

def test_layers_from_zip_members_one_row_per_shp():
    rows = layers.layers_from_zip_members("s" * 64, "X_SHP.zip",
        ["A/ST_20180508_WaterExtent_X.shp", "A/ST_20180508_WaterExtent_X.dbf", "A/readme.txt"])
    assert len(rows) == 1 and rows[0]["layer"] == "ST_20180508_WaterExtent_X" and rows[0]["source"] == "shp"

def test_rows_match_columns():
    for r in layers.layers_from_ogrinfo("s" * 64, "X.zip", INFO):
        assert list(r) == layers.LAYERS_COLUMNS
```

- [ ] **Step 2: Run to verify failure** — `uv run --group etl pytest tests/unosat/test_layers.py -q` → ImportError.

- [ ] **Step 3: Implement `src/gie/unosat/layers.py`**

```python
"""Inventory of every layer inside every archived flood/cyclone zip (spec §3 prerequisite).

GDB feature classes come from `ogrinfo -json` (name, geometry type, feature count, fields and
their domain bindings); SHP members from the bronze zip inventory. This table is what the layer
grammar is tested against and what silver iterates over.
"""
from __future__ import annotations

LAYERS_COLUMNS = ["sha256", "zip_basename", "source", "layer", "geometry_type",
                  "feature_count", "fields", "field_domains"]

def layers_from_ogrinfo(sha256: str, zip_basename: str, info: dict) -> list[dict]:
    rows = []
    for lyr in info.get("layers") or []:
        gf = lyr.get("geometryFields") or []
        rows.append({
            "sha256": sha256, "zip_basename": zip_basename, "source": "gdb",
            "layer": lyr["name"],
            "geometry_type": gf[0].get("type") if gf else None,
            "feature_count": lyr.get("featureCount"),
            "fields": [f["name"] for f in lyr.get("fields") or []],
            "field_domains": {f["name"]: f["domainName"] for f in lyr.get("fields") or [] if f.get("domainName")},
        })
    return rows

def layers_from_zip_members(sha256: str, zip_basename: str, members: list[str]) -> list[dict]:
    return [{
        "sha256": sha256, "zip_basename": zip_basename, "source": "shp",
        "layer": m.split("/")[-1][:-4], "geometry_type": None, "feature_count": None,
        "fields": None, "field_domains": None,
    } for m in members if m.lower().endswith(".shp")]
```

CLI `pipelines/unosat/layers.py`: `add_common_args`, `meta.bootstrap`; select flood/cyclone uploaded rows, distinct `sha256`; for GDB zips reuse `domains.domains_for_gdb_zip`'s extraction pattern but call `ogrinfo_json` and `layers_from_ogrinfo` (factor a shared `domains.extract_gdb_dirs(zip_path) -> (tmpdir, [gdb paths])` context manager if needed — keep `domains.py` behaviour unchanged); for SHP zips read members from `zip_contents.parquet` for that sha. Resumable via `layers_status.parquet` (skip done shas), checkpoint every 25 with `persist_frames`-style rows-then-status writes (reuse `domains.persist_frames` pattern via a small generic `write_two_tables(work_dir, rows_df, rows_name, status_df, status_name)` in `domains.py` if that avoids duplication; otherwise mirror). Upload both `_meta` files at the end. Print status counts.

- [ ] **Step 4: Run tests, lint, commit** — `unosat: layer inventory over bronze (GDB feature classes + SHP members)`.

- [ ] **Step 5: Run for real (controller):** `pipelines/unosat/layers.py` → expect ~1,350 shas, ~3,000+ GDB layers with geometry, 2,600 distinct SHP names. Record counts; export the distinct layer names (GDB + SHP, geometry layers only) to `tests/unosat/fixtures/layer_names_flood.txt`, one per line, committed (small text file).

---

### Task 2: Layer-name grammar

**Files:** Create `src/gie/unosat/grammar.py`, `tests/unosat/test_grammar.py`, `tests/unosat/fixtures/layer_names_flood.txt` (from Task 1 Step 5; until then use the 2,600 SHP names exported during design — controller supplies the file).

**Interfaces:** `@dataclass(frozen=True) LayerName: raw, sensor (normalised or "multiple"/None), sensor_raw, dates (tuple[date,...]), window (tuple[date,date]|None), kind (one of the layer_kind values, or "footprint"/"not_analysed", or "skip", or None), table ("observed_event"|"coverage"|None), area (str), malformed_tokens (tuple[str,...])`; `parse(name: str) -> LayerName`; `SENSOR_ALIASES: dict`; `KIND_RULES: tuple[tuple[str, str, str]]` (needle, table, kind) in precedence order exactly as the spec table, plus `SKIP_NEEDLES`.

- [ ] **Step 1: Tests** (real names; expected values from the spec §3 grammar):

```python
from datetime import date
from pathlib import Path
from gie.unosat import grammar

def P(n): return grammar.parse(n)

def test_simple_flood_extent():
    ln = P("VIIRS_20211119_20211123_FloodExtent_SouthSudan")
    assert ln.sensor == "VIIRS" and ln.window == (date(2021,11,19), date(2021,11,23))
    assert ln.kind == "flood" and ln.table == "observed_event" and ln.area == "SouthSudan"

def test_fused_sensor_date_and_underscore_kind():
    ln = P("ST20190330_Golestan_Flood_Water")
    assert ln.sensor == "Sentinel-1" and ln.dates == (date(2019,3,30),) and ln.kind == "flood"

def test_leading_unosat_and_multisensor():
    ln = P("UNOSAT_Multisensor_20260826_20260828_FloodExtent")
    assert ln.sensor == "multiple" and ln.window == (date(2026,8,26), date(2026,8,28)) and ln.kind == "flood"

def test_multi_sensor_many_dates_is_window_min_max():
    ln = P("ST3_20230606_20230607_20230609_ST2_20230608_ICEYE_20230607_FloodExtent_KhersonskaOblast")
    assert ln.sensor == "multiple" and ln.window == (date(2023,6,6), date(2023,6,9)) and ln.kind == "flood"

def test_precedence_preflood_and_maximum_before_flood():
    assert P("S1_20220224_PreFloodWaterExtent_Betroka").kind == "water_pre"
    assert P("VIIRS_20221224_20221228_MaximumFloodWaterExtent_SouthSudan").kind == "aggregate_max"
    assert P("S1_20230317_MinimumFloodWaterExtent_MWI").kind == "aggregate_min"
    assert P("RCM2_20220228_WaterExtent_Ifotaka").kind == "water"
    assert P("ST_20170302_Omusati_SatelliteDetectedSurfaceWater").kind == "water"

def test_coverage_and_skip():
    assert P("RCM2_20220228_AnalysisExtent_Ifotaka").table == "coverage" and P("RCM2_20220228_AnalysisExtent_Ifotaka").kind == "footprint"
    assert P("VIIRS_20190930_20191019_CloudObstruction_SouthSudan").kind == "not_analysed"
    assert P("WV3_20230607_AffectedHarbour_Kherson").kind == "skip"

def test_malformed_date_recorded_not_parsed():
    ln = P("RS2_0150118_Flood")
    assert ln.dates == () and ln.malformed_tokens == ("0150118",) and ln.kind == "flood"

def test_fixture_coverage_counts():
    names = Path(__file__).parent.joinpath("fixtures/layer_names_flood.txt").read_text().splitlines()
    parsed = [grammar.parse(n) for n in names]
    unmatched = [p.raw for p in parsed if p.kind is None]
    # ≤ 4 % unmatched and every unmatched name is listed in the fixture's sibling file
    assert len(unmatched) / len(names) <= 0.04, unmatched[:20]
    expected = set(Path(__file__).parent.joinpath("fixtures/layer_names_unmatched.txt").read_text().splitlines())
    assert set(unmatched) == expected
```

- [ ] **Step 2: Fail** — ImportError.
- [ ] **Step 3: Implement** `grammar.py`: tokenise on `_`; drop leading `UNOSAT`; for each token: `re.fullmatch(r"\d{8}", t)` → try `datetime.strptime(t, "%Y%m%d").date()` else malformed; `re.fullmatch(r"([A-Za-z]+)(\d{8})", t)` → sensor prefix + date; sensor = first alphabetic token (normalised through `SENSOR_ALIASES`: `ST`/`ST1`/`S1`→`Sentinel-1`, `ST2`/`S2`→`Sentinel-2`, `ST3`/`S3`→`Sentinel-3`, `PHR`→`Pleiades`, `PL`/`PlanetScope`/`PT`→`Planet`, `RS`/`RS2`→`RADARSAT-2`, `RCM`/`RCM1`/`RCM2`→`RCM`, `WV`/`WV1`/`WV2`/`WV3`/`WV03`→`WorldView`, `L8`/`LS8`/`L9`/`LS`→`Landsat`, `TSX`/`TX`/`TDX`→`TerraSAR-X`, `GE01`→`GeoEye-1`, `VIIRS`→`VIIRS`, `MODIS`→`MODIS`, `ICEYE`→`ICEYE`, `Multisensor`/`Multisensors`/`Multi`→`multiple`), unknown alphabetic first token kept as `sensor_raw` with `sensor=None`; if more than one alphabetic sensor-like token precedes the kind → `multiple`; kind from `KIND_RULES` by casefolded substring on the whole name in precedence order (`cloudobstruction`, `analysisextent`/`analysis_extent`/`areaofinterest`/`aoi`, `permanentwater`/`prefloodwater`/`preflood`/`archivewater`, `maximumflood`/`maxflood`/`cumulative`, `minimumflood`, `floodextent`/`flood_water`/`floodwater`/`flood`, `satellitedetected…`/`waterextent`/`water`, trailing `extent`); `SKIP_NEEDLES` checked first (`damage, structure, building, idp, shelter, landslide, road, bridge, harbour, health, cropland, waterway`); area = remaining tokens joined by `_`. Dates: 1 → `dates=(d,)`, `window=None`; ≥2 → `window=(min,max)`.
- [ ] **Step 4: Iterate the fixture test**: run over the fixture; write the unmatched list to `tests/unosat/fixtures/layer_names_unmatched.txt`; review it — every entry must be a non-label layer (impact, admin, buffers); if a water layer appears there, extend the vocabulary, not the exclusion list.
- [ ] **Step 5: Lint, commit** — `unosat: layer-name grammar with real-name fixture (≥96 % classified)`.

---

### Task 3: Water-class resolution and sensor class

**Files:** Create `src/gie/unosat/classes.py`, `tests/unosat/test_classes.py`.

**Interfaces:** `CLASS_TEXT_TO_KIND: dict[str, str]` (casefolded, whitespace-normalised keys covering every value of the three domains: `preflood water`, `archive water extent / pre-flood water`, `permanent water` → `water_pre`; `flood water` → `flood`; `satellite detected water`, `satellite detected waters` → `water`; `flood-affected land / possible flood water`, `satellite detected water / possible saturated soil`, `possible saturated, wet soil/ possible flood water`, `possible satuated, wet soil`, `probable flash flood-affected land` → `flood_possible`; `aquaculture (wet rice)`, `aquaculture`, `swamp/marsh/mangrove`, `swamp / marsh / mangrove`, `snow cover`, `tsunami-affected land` → `other_water`; `maximum flood water extent (cumulative)`, `maximum satellite observed water (cumulative)` → `aggregate_max`); `normalise_text(s) -> str`; `resolve_class(raw_value, *, domain_lookup: dict[str,str] | None, decoded_text: str | None) -> tuple[str | None, str]` returning `(kind, class_method)`; `is_unfilled(record: dict) -> bool` (class/sensor/confidence all 0/None); `final_kind(layer_kind_from_name, polygon_kind, unfilled) -> tuple[str, bool]` (kind, conflict); `sensor_class(sensor: str | None) -> str` (`Sentinel-1/RADARSAT-2/RCM/TerraSAR-X/ICEYE/COSMO*` → `sar`; `Pleiades/WorldView/GeoEye-1/SkySat/Planet/SPOT/Kompsat` → `optical_vhr`; `Sentinel-2/Landsat` → `optical_hr`; `VIIRS/MODIS/Sentinel-3` → `optical_coarse`; `multiple` → `multiple`; else `unknown`).

- [ ] Tests: every domain value in the table resolves (parametrised over the literal list above, incl. unicode/odd spacing); GDB code with domain → `domain`; code with no entry → `(None, "unresolved_code")`; SHP text → `text`; decoded column beats raw code → `decoded_column`; unfilled record → layer-name kind with `layer_name`; conflict flag when polygon `water_pre` inside a `flood` layer; `sensor_class` mapping incl. `unknown`.
- [ ] Implement; lint; commit — `unosat: water-class resolution against the three domains; sensor classes`.

---

### Task 4: Layer readers and content hash

**Files:** Create `src/gie/unosat/readers.py`, `tests/unosat/test_readers.py`.

**Interfaces:** `read_gdb_layer(gdb_path: Path, layer: str) -> gpd.GeoDataFrame`; `read_shp_member(zip_path: Path, member: str) -> gpd.GeoDataFrame` (via `pyogrio.read_dataframe(f"zip://{zip_path}!{member}")`); `to_wgs84(gdf) -> tuple[gpd.GeoDataFrame, str]` (returns source CRS string; raises `ValueError` if CRS missing); `attrs_json(row) -> str` (all non-geometry columns, JSON with `default=str`); `content_hash(gdf) -> str` (sha256 over the sorted concatenation of WKB hex + attrs_json per feature, so identical layers hash identically regardless of file bytes); `extract_gdbs(zip_path) -> contextmanager yielding list[Path]` (shared with `domains.py`: move `domains_for_gdb_zip`'s extraction there and have domains call it — behaviour unchanged, tests must still pass).

- [ ] Tests with a synthetic shapefile written by geopandas into a zip (EPSG:32636 to test reprojection) and a GDB read test guarded by `shutil.which("ogrinfo")`/pyogrio OpenFileGDB availability using a tiny GDB created by `pyogrio.write_dataframe(..., driver="OpenFileGDB")` (skip if the driver cannot write); `content_hash` equal for two frames with same content in different row order; different for a changed attribute.
- [ ] Implement; lint; commit — `unosat: layer readers (GDB, SHP-in-zip), WGS84 reprojection, deterministic content hash`.

---

### Task 5: Acquisition resolution

**Files:** Create `src/gie/unosat/acquisition.py`, `tests/unosat/test_acquisition.py`.

**Interfaces:** `resolve_acq(name: grammar.LayerName, sensor_dates: pd.Series) -> dict` with keys `acq_datetime, acq_window_start, acq_window_end, acq_precision, acq_method, acq_conflict` (per layer, using the most common non-null per-polygon sensor date; if polygons carry several distinct dates, the layer is split upstream by the silver builder per distinct date — see Task 6). Rules exactly as spec §3 "Acquisition": filename single date + agreeing attribute → `date/attribute`; filename window containing attribute → `window/attribute`; filename only → `date/filename` (or `window/filename`); attribute only → `date/attribute`; disagreement → `window` spanning both, `acq_conflict=True`, method `attribute`; nothing → `none/none`.

- [ ] Tests for each rule incl. the real disagreement cases (`20200305` filename vs `20200503` attribute → window 2020-03-05..2020-05-03, conflict).
- [ ] Implement; lint; commit — `unosat: acquisition resolution (filename vs sensor date, conflicts kept visible)`.

---

### Task 6: Silver builder and CLI

**Files:** Create `src/gie/unosat/silver.py`, `pipelines/unosat/silver.py`, `tests/unosat/test_silver.py`; modify spec §3 layout sentence.

**Interfaces:**
- `OBSERVED_COLUMNS`, `COVERAGE_COLUMNS`, `SOURCES_COLUMNS`, `PROCESSING_COLUMNS` per spec §3 (observed adds `content_hash`, `sha256`, `target_ids`).
- `build_layer(code, code_method, ln: grammar.LayerName, gdf: gpd.GeoDataFrame, *, source: str, sha256: str, target_ids: list[str], domain_lookup: dict[str, dict[str, str]] | None) -> tuple[pd.DataFrame | gpd.GeoDataFrame, str, dict]` → (rows for observed_event OR coverage, table name, processing record). Splits by distinct per-polygon sensor date before `resolve_acq`. Skips (`skipped_non_water`) when `ln.kind == "skip"`; `unclassified` when `ln.kind is None`; `no_date` when `acq_precision == "none"`.
- `silver_layer_path(table, code, content_hash) -> str`; `write_layer(store, path, gdf)`.
- CLI: iterate flood/cyclone datasets from the ledger; per dataset pick the GDB zip when present else the SHP zip (`geometry_source`); for GDB, cross-check SHP presence of each layer name when a SHP zip exists in the same dataset (`shp_gdb_mismatch` = layer names present in one but not the other, recorded on the processing row, no reads of SHP data unless GDB-only-missing); per layer: read (`readers`), `content_hash`, skip if `silver_layer_path` exists in blob (idempotent; record `ok` with `reused=True`), else build + write; `sources` rows accumulated per code and written per code at the end; processing ledger checkpointed every 25 layers (rows-then-status pattern) and uploaded to `_meta/`. `--codes` filter, `--limit`, resumable by `(sha256, layer)` in the processing ledger. A GDAL read failure on one layer → `unreadable` with error text, continue; anything else raises.

- [ ] Tests: `build_layer` on a synthetic GeoDataFrame with `Water_Class` codes + a domain lookup → observed rows with resolved kinds, conflict flags, acq columns; a coverage layer → coverage rows with role; a skip layer → processing `skipped_non_water` and no rows; a layer whose polygons carry two sensor dates → two groups with distinct `acq_datetime`; `content_hash` present and equal across two identical inputs; idempotent write (MemoryStore) skips the second identical layer.
- [ ] Spec: change the silver layout sentence to the per-layer-file layout with the one-line justification (idempotent, deduplicates re-shipped layers by construction).
- [ ] Implement; lint; commit — `unosat: silver builder — one GeoParquet per distinct layer content under code partitions; processing ledger`.
- [ ] **Run for real (controller):** first `--limit 20`, inspect a partition, then the full run (911 datasets; expect tens of minutes). Record processing status counts.

---

### Task 7: Gold v2 builder and CLI

**Files:** Create `src/gie/unosat/gold.py`, `pipelines/unosat/gold.py`, `tests/unosat/test_gold.py`, `docs/decisions/0034-flood-label-gold-v2-water-and-flood-geometries.md`.

**Interfaces:** `INDEX_COLUMNS` per spec §4; `build_code(code, observed: gpd.GeoDataFrame, coverage: gpd.GeoDataFrame, meta: dict) -> tuple[gpd.GeoDataFrame labels, pd.DataFrame index]`: `make_valid` both inputs; group observed by `(area_label, acq_start, acq_end)` where `acq_start = acq_window_start.fillna(acq_datetime)`, `acq_end = acq_window_end.fillna(acq_datetime)`; exclude `acq_precision == "none"`; per group `geom_water` = union of kinds {water, water_pre, flood}, `geom_flood` = union of {flood} (null if the group has no `flood` rows AND no `flood`-kind layer), `geom_possible` = union of {flood_possible}; `geom_valid` = union of coverage `footprint` rows for the same `(area_label, acq interval)` minus union of `not_analysed` (basis `footprint_minus_cloud` / `footprint` / `none`); areas in EPSG:6933; `sensor` = most common sensor in the group, `sensor_class` via `classes.sensor_class`; `excluded_aggregate_n` = count of aggregate/other_water rows dropped; `label_day` when start/end on the same day. Labels GeoDataFrame has geometry columns `geom_water, geom_flood, geom_possible, geom_valid` (primary `geom_water`) plus `label_source="unosat", code, aoi, acq_start, acq_end, label_day, valid_basis`.
- CLI: per code read all silver layer files for the two tables (list blobs under the partition, read each, concat), build, write `gold/labels/code={code}/data.parquet` and `gold/_index_parts/code={code}.parquet`; at the end concat all index parts into `gold/label_index.parquet`. `--codes`, `--limit`. Reuse-or-mirror the CEMS gold writing pattern (`pipelines/cems_flood/gold.py`), but geometry columns per spec v2.

- [ ] Tests on synthetic silver frames: water = flood ∪ pre-flood; flood separable; possible separate; valid mask subtracts clouds; aggregate rows excluded and counted; two acquisition intervals → two rows; areas positive; `label_day` set only when same day; round-trip write/read of the multi-geometry GeoParquet via `geopandas.read_parquet` preserves all four geometry columns.
- [ ] ADR-0034 (MADR, from `docs/decisions/template.md`): shared gold v2 with `label_source`, `sensor_class`, separate water/flood/possible geometries; supersedes the gold section of ADR-0029; rejected: flood-only gold (loses the water target the fusion spec chose), per-source gold schemas (two readers).
- [ ] Implement; lint; commit — `unosat: gold v2 — water/flood/possible geometries + valid mask per acquisition; label_index; ADR-0034`.
- [ ] **Run for real (controller):** full gold build; record label-set counts by `sensor_class` and `acq_precision`.

---

### Task 8: Silver/gold audit rules and reporting

**Files:** Modify `src/gie/unosat/audit.py`, `pipelines/unosat/audit.py`, `tests/unosat/test_audit.py`.

- Rules (spec §5): **S1** processing ledger covers every `(sha256, layer)` in `layers.parquet` for flood/cyclone GDB-or-SHP-chosen sources; **S2** every code with ≥1 `ok` observed layer has an `observed_event` partition, and every code with coverage layers has a `coverage` partition; **S3** `acq_datetime`/window years within [2005, now] and within one year of the event-code date; **S4** vocabularies within the documented sets (`layer_kind`, `role`, `class_method`, `acq_precision`, `acq_method`, `geometry_source`, processing `status`); **S5** `unclassified` share per code ≤ 4 % else listed; **S6** every GDB-sourced code with a SHP sibling has `shp_gdb_mismatch` recorded (may be empty list); **G1** every gold row has `geom_valid` or `valid_basis == "none"`; **G2** no `aggregate_*`/`other_water` polygons contributed to gold geometries (assert `excluded_aggregate_n` accounting: sum over index equals count of such rows in silver for that code). Each returns `(ok, detail)`; CLI gains `--silver` and `--gold` flags (default: all three sections), prints label-set counts by `sensor_class × acq_precision` and by country as the report, writes `audit_stale_codes.txt`.
- [ ] Tests for each rule with synthetic frames (pass and fail).
- [ ] Implement; lint; commit — `unosat: audit S1–S6, G1–G2; stale-code list; label-coverage summary`.
- [ ] **Run for real (controller):** audit must pass; iterate with the defect-fix loop (fix → audit → reprocess stale codes → audit) if not.

---

### Task 9: Docs, data ledger, README, PR

- README `pipelines/unosat/README.md`: silver/gold sections (layouts, run commands, vocabularies, the GDB-first rule, the per-layer-file idempotency, the water/flood/possible split, `sensor_class`).
- `data_ledger.md`: rows for `unosat | silver` and `unosat | gold` with real counts from the runs.
- Spec: mark §Testing phase 2–3 items as done where they are; record the per-layer-file layout deviation (done in Task 6).
- Memory/knowledge base: the KB page `pipelines/cems-flood-archive.md` gets a sibling `pipelines/unosat-flood-archive.md` (KB worktree, PR) — controller task, after merge.
- Commit — `unosat: silver/gold docs, data ledger rows`; open PR `feat/unosat-silver-gold` → `feat/unosat-archive` (or `v1` once #128 merges).

---

## Self-review against the spec

- §3 Silver: GDB-first ✔ (Task 6), unit of work per layer content ✔ (content hash, per-layer files), event code rule ✔, grammar ✔ (Task 2, incl. UNOSAT prefix, fused tokens, multi-date, malformed), per-polygon class ✔ (Task 3 covers all three domains; spec table extended with `Satellite Detected Waters` and `Snow Cover` values found in the real domains), precedence/unfilled/conflict ✔, canonical columns ✔, acquisition rules ✔ (Task 5), coverage/sources ✔, processing ledger ✔. Deviation: per-layer files instead of `data.parquet` per code — recorded in spec by Task 6.
- §4 Gold: grain ✔, four geometries ✔, exclusions counted ✔, index columns ✔ incl. `sensor_class`, areas in 6933 ✔, `label_source` ✔. CEMS v2 rebuild remains a follow-up (not this plan).
- §5: S1–S6, G1–G2 ✔ (Task 8).
- Placeholders: none. Types consistent: `LayerName` fields used by Tasks 5–6 match Task 2; `resolve_class`/`final_kind` used by Task 6 match Task 3; `content_hash` and readers by Task 6 match Task 4.
