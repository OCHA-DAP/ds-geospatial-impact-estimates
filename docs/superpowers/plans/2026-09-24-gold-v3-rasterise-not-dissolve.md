# Gold v3: rasterise label sets, don't dissolve them

**Goal:** produce UNOSAT flood labels for the fusion model in seconds per event
by burning silver layers onto the 30 arcsec grid instead of unioning them.

**Why:** the fusion model (the only consumer; the user is building it) reads
labels as 30 arcsec cells. Gold v2 dissolves polygonised-raster geometry in
vector space — `make_valid` + `union_all` — which is superlinear in vertices
per geometry and cost 13 h 58 min on one event without finishing. Burning is
a logical OR, footprint-minus-cloud is AND NOT, and a scanline rasteriser
needs no validity. Everything durable in gold (layer-name grammar, class
resolution, acquisition intervals, coverage matching) is the grouping, which
is free; only the dissolve is expensive. ADR-0037 records the decision.

**Spec:** ds-flood-gfm `docs/superpowers/specs/2026-09-18-flood-fusion-design.md`
(grid: 1/120°, EPSG:4326, integer row/col identity; labels rasterised with a
valid mask where 0 = unobserved, not dry).

## Proof of concept (this commit)

`pipelines/unosat/gold_raster_poc.py` — one event from the local silver
mirror → one 4-band uint8 GeoTIFF per label set (water, flood, possible,
valid), on a window of the global grid snapped to its cells. Reuses gold's
`_prepare(method="none")` and grouping. Prints per-label-set timings.
Tests: `tests/unosat/test_gold_raster_poc.py` (grid snapping, OR semantics,
invalid input accepted, valid = footprint AND NOT cloud).

Try it after the current run finishes (it shares the machine):
```
uv run --group etl --group api python pipelines/unosat/gold_raster_poc.py \
    --codes FL20250812CPV            # 7 polygons: the floor
uv run --group etl --group api python pipelines/unosat/gold_raster_poc.py \
    --codes FL20220728NER            # 672k parts / 11.6M vertices: >1h35m under snap
uv run --group etl --group api python pipelines/unosat/gold_raster_poc.py \
    --codes FL20220418ZAF            # 30M vertices: 13h58m under validate, unfinished
```
Acceptance for "really seconds": NER and ZAF each under 60 s end to end.

## If it holds: Task list for gold v3

1. **Contract.** `gold/v3/labels/code={code}/{area}_{start}_{end}.tif` (4-band
   uint8, deflate, tiled) + `gold/v3/label_index.parquet` with the v2 index
   columns minus the km² areas, plus `cells`, `water_cells`, `valid_cells`,
   `tif_path`. Areas in km² become cell counts × cell area (approximate at
   30 arcsec; state it).
2. **Library.** Move `grid_for`, `burn`, `rasterise_label_set`,
   `build_code_raster` from the PoC into `src/gie/unosat/gold_raster.py`;
   keep the PoC as a thin CLI. Coverage matching: call gold's `_valid_mask`
   selection logic (extract the row-selection half from the union half) so
   v2 and v3 agree on WHICH footprint applies; only the geometry step differs.
3. **Pipeline.** `pipelines/unosat/gold_v3.py`: blob-backed via
   `gold.read_partition`, resumable per event (skip if tif set + index part
   exist), same fail-loud rules. No `--geometry-method`: there is no geometry
   step to choose.
4. **Audit.** G3: every v2 label set has a v3 tif; G4: for a sample of events,
   v3 water cells ≈ rasterised v2 `geom_water` (same burn) — the
   equivalence check between contracts.
5. **Fusion adapter (ds-flood-gfm).** `fusion/labels/unosat.py` reads
   `gold/v3/label_index.parquet` + tifs directly onto `Grid(res_arcsec=30)`.
6. **ADR-0037 → accepted**; ADR-0034 marked superseded-in-part (v2 stays for
   any vector consumer; v3 is the fusion path).

Not in scope: rebuilding v2. It exists, is audited, and records its method per
event (ADR-0036).
