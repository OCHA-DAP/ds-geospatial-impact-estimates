# Overnight handoff — IMPACT SAR source + the gold-rebuild blocker

> Working note, **not committed**. Delete or fold into a ticket once read.

## TL;DR
The CEMS + Microsoft data overhaul **shipped to production** (live, verified). The
new **IMPACT SAR damage-proxy source** is now **bronze + silver + gold complete**
(the gold-rebuild hang was found and fixed — see below). The **dev gold has all 3
sources**, verified. Remaining: **serving + frontend** to surface SAR in the app,
then deploy. Production is healthy on the 2-source data until then.

## RESOLVED — the gold-rebuild hang
**Cause:** the facts block built one giant query — 15 per-source-per-grain
aggregations `UNION ALL`'d then `UNPIVOT`'d — which wedged the DuckDB executor at 3
sources (0% CPU in `WaitForTask`, indefinitely). The 2-source form (10 branches)
had been fine. Root cause inside DuckDB still not fully explained, but:
**Fix:** run each per-grain `GROUP BY` as its own query and `concat`+`melt` in
pandas — **the exact pattern `_area_facts` / `_cems_breakdown` already use**. The
facts block was the lone holdout on the single-query form. Clean + consistent, not
a hack. Gold built end-to-end.
**Verified dev gold:** 3 sources present; SAR = 123,995 damaged buildings conserved
silver→gold (92 adm3 units); all 123,995 in `building_flags` (524,078 total).

## Shipped to production tonight (verified)
- CEMS overhaul: version supersession (real manifest fields); two damage layers —
  `builtUpA` (coarse blocks) + `builtUpP` (per-building points); points snapped to
  Overture footprints (20 m) so CEMS is building-level & comparable to Microsoft
  (Caraballeda 2,881 area-swept → 213 precise points).
- Hover redesign (both sources; CEMS point-vs-coarse; extrapolation off the surface).
- New Microsoft AOIs (Catia La Mar East, La Guaira Surrounding); `la_guaira_east`
  superseded at gold level.
- Aragua Overture base pulled (~1.5M buildings; CEMS Santa Cruz / AOI05).
- Excel export glossary corrected.
- 19/19 verification passing for the 2-source gold.

## IMPACT SAR source — status
- Methodology: Sentinel-1 unsupervised z-score change (post-event 06-25 vs 1-yr
  baseline), masked at z>0.7. A **hotspot/gap screen, NOT confirmed damage**.
- ✅ Bronze: 465 MB GeoTIFF in blob (`source=impact_initiatives`). `pipelines/ingest_impact_sar.py` (committed).
- ✅ Silver: **123,995 damaged buildings** (17,752 high-confidence z≥1.0), graded to
  the CEMS `damage_class` model (0.7–1.0 Possibly, ≥1.0 Damaged); footprint = raster
  bounds. `pipelines/harmonize_impact_sar.py`.
- ✅ ADR-0008 (design + the temporary "damaged-only on `building_flags`" decision).
- ✅ Gold: **built** (dev), all 3 sources, verified. 614,675 fact rows.

## Code state (all UNCOMMITTED — review before committing)
`harmonize_common.py` has the working changes, not yet committed:
- SAR wired in as the 3rd source (`SOURCES`, `located` columns, `building_flags`).
- **Facts block** switched to per-grain queries + pandas melt (the fix; matches
  `_area_facts`/`_cems_breakdown`). The old `UNION ALL`+`UNPIVOT` form is gone.
- **Local-mirror download** (`_local`/`_local_base`/`_fetch`) — added because the
  blob endpoint was degraded last night and DuckDB's azure-extension reads stalled
  with no timeout. If the network is healthy, this can be reverted to `az://` reads;
  it writes a `/tmp/gie_*_local` cache. Worth keeping as a resilient option.
- **Clean non-azure DuckDB connection** for the compute (inputs are local now).
- **Chunked, timeout-guarded uploads** (`_upload`) — survives the flaky write
  endpoint (the building_flags write stalled twice last night and still got through).
- A few progress `print()`s (located built / facts aggregated / building_flags) —
  keep or drop, harmless.

Committed/clean: `ingest_impact_sar.py`, `harmonize_impact_sar.py`, ADR-0008.
The gold **in blob is now 3-source (dev)**. Production still serves the prior
2-source gold until a deploy.

## Remaining work
1. **Serving** (`src/gie/serving.py`): add `impact_initiatives` to the sources list /
   labels / `_COMMON_PIVOT` so the API returns SAR.
2. **Frontend** (`web/src/main.ts`): SAR as a selectable 3rd source + map layer +
   hover; carry the "screening, not confirmed damage" caveat (ADR-0008).
3. Deploy to staging → prod.
4. Per ADR-0008 the per-building layer is intentionally **damaged-only** until
   PMTiles (the ~1.86M analysed set isn't materialised in `building_flags`).
5. Optional cleanup: review/commit the uncommitted `harmonize_common.py` changes;
   decide whether to keep the local-mirror path or revert to `az://`.
