# DATA_MAP — confirmed schemas for the performance analysis

Ground truth from live reads by the three mapper agents (2026-07-05). All paths under
`az://projects/ds-geospatial-impact-estimates/`, read stage `dev`, `adm0=VE`. Read via
`ocha_stratus.load_blob_data` + `gpd.read_parquet`, or `gie.db.connect()` (DuckDB-on-blob).

## CEMS — GROUND TRUTH (`source=copernicus_ems`)

`silver/.../builtup_damage.parquet` — **3,427** graded features, EPSG:4326, one file split by
`layer_type`. **Damaged-only inventory: no "surveyed-undamaged" record exists.**

| layer_type | what | rows | is_latest | grades (Possibly/Damaged/Destroyed → class 1/2/3) |
|---|---|---|---|---|
| `area` (builtUpA) | coarse blocks, `area_m2`>0 | **355** | all **False** (superseded, never reach gold) | 171 / 172 / 12 |
| `point` (builtUpP) | per-building points, `area_m2`=0 | **3,072** | all **True** (gold built from these) | 1,549 / 828 / 695 |

Key fields: `aoi_number`, `aoi_name`, `layer_type`, `ems_grade`, `damage_class` (1/2/3),
`is_latest`, `version_number`, `monitoring_number` (0=initial, ≥1=monitoring), `area_m2`, `geometry`.

Per-AOI (area / point): Caracas(2) 17/20 · Santa Cruz(5) 0/3 · Moron(6) 129/96 · San Felipe(8)
43/183 · **Caraballeda(12) 166/2,770** (dominant).

`silver/.../analysed_extent.parquet` — **35** polygons = valid analysed area
`(AOI ∩ imageFootprint) − notAnalysed(cloud)`. Sibling `coverage_detail.parquet` stacks
analysed + not_analysed with a `kind` column. **Coarse (initial) and point (monitoring) products
have their own per-product extents** — use the initial-product extent when scoring coarse blocks.

`gold/.../damage_facts.parquet` — 332 rows, **points-only**, tidy long. `damaged_area_m2` is dead
(0, points have no area) — use `damage_features` (count). Not used as scoring basis (see DESIGN).

## Comparison sources

| source | silver file | rows | geom? | damaged def. | building key | analysed AOI |
|---|---|---|---|---|---|---|
| **impact v2** | `impact_initiatives/.../building_damage.parquet` | 81,437 | ✅ footprints | SAR amplitude ≥50% of footprint (all class 2) | own geom + Overture `id` (68,004 non-null / 13,433 null) | ✅ swath polygon ~32,712 km² |
| **impact v1** (raster) | *(overwritten — must re-materialise)* | 123,941 | ❌ (id) | z≥0.7 raster sampled @ Overture centroid; 0.7–1.0→c1, ≥1.0→c2 | Overture `id` | ✅ swath-clipped box |
| **osu** | `osu/.../building_damage.parquet` | 58,870 | ❌ (id table) | S1 coherence ≥50% footprint, ShakeMap-calibrated ≤1% false-alarm (all class 2) | **Overture `id`** (99.4%, cleanest) | ✅ analyzed-area polygon |
| **microsoft** | `microsoft/.../footprints.parquet` | 72,162 (8,410 dmg / 63,752 undmg) | ✅ footprints | binary `damaged==1` (optical CNN) | **own footprints, no id** | ✅ valid-area mask |
| **unep_debris** | `unep_debris/.../debris.parquet` | 96,046 | ✅ GBA MultiPolygon | **none — threshold `debris_tonnes`>0** | **own GBA footprints (finer than Overture)** | ❌ **detected-only** |

Notes: OSU bronze `EMSR884_damage_20260625_v0.gpkg` (~2.7M) carries `damage` 0/1 + `within_coverage`
→ OSU's own analysed-but-undamaged negatives. Microsoft silver already carries negatives.
**impact v1 silver is overwritten by v2 at the same blob key** — re-run `harmonize_impact_sar.py`
to a distinct path (or re-derive from bronze `.tif`) to score v1 and v2 side by side.

## Snap-to-Overture error (why gold is not the scoring basis) — exploratory/0003 @ 20 m

| source | native | snapped to Overture | dropped (no Overture w/in 20 m) | note |
|---|---|---|---|---|
| Microsoft | 8,410 | 8,342 | ~0 | near-Overture, −1% |
| CEMS points | 3,072 | 2,708 | 81 (**2.6%**) + 283 collapsed | reference itself distorted |
| UNEP debris | 96,046 | 75,656 | ~2% | **−21% granularity collapse** (GBA finer than Overture) |

The gap is footprint-**granularity collapse**, not missing damage — it conflates detection error
with resolution, so it must not be baked into scoring (ADR-0017). `gold/.../facts.parquet` (current
= 4,524,579 rows, h3 res-8 + adm0-3, long) and `building_flags.parquet` (per-building but filtered,
lacks full analysed sets → cannot build true-negatives) are the **operational** comparison only.
