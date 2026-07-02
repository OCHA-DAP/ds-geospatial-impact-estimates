# IMPACT Sentinel-1 damage v2 — is it safe to ingest and fully supersede v1?

> **Status:** complete & verified (2026-07-02).
> **Verdict: yes — footprints are exactly Overture, the AOI fully envelops v1, and
> the counts are sound.** One design consequence: key on geometry, not an id-join.
> Analysis: [`analysis.py`](analysis.py) · Feeds [ADR-0015](../../docs/decisions/0015-impact-v2-vector-damage.md).

## Question

IMPACT Initiatives delivered a **v2** damage product for the VE earthquake — a
*vector* GeoPackage of damaged building footprints plus an analysed-area polygon,
replacing the v1 10 m SAR-proxy *raster* (ADR-0008). The analyst asks us to update
the app with v2, superseding v1. Before we do: are the footprints really our common
Overture base, does v2 cover (envelop) v1 so the supersede is clean, is it
damaged-only, are there damage classes to standardise, and are the counts sound?

## Data (bronze)

`bronze/source=impact_initiatives/adm0=VE/` — both EPSG:32619 (UTM 19N):

- `...Sentinel1_damaged_..._v2.gpkg` — **81,437** damaged building footprints.
  Fields: `id` (Overture GERS), `bdg_id` (unique per row), `source`, `bdg_sfc`
  (footprint area m²), `b_aff_sf` (affected area m²), `class`/`subtype` (Overture
  type), adm0–adm4.
- `...analyzed_area_..._v2.gpkg` — one AOI MultiPolygon, **~32,712 km²**.

## Findings

| # | Check | Result |
|---|---|---|
| 1 | Format | **Vector** (was raster) — needs a new adapter. |
| 2 | Footprints = our Overture base? | **Exactly.** 100% `id` match in every state our base covers; geometry **IoU = 1.000** (100% of a La Guaira sample ≥0.99). Same UUID id scheme. |
| 3 | Full set or damaged-only? | **Damaged-only** — every row has `b_aff_sf` > 0. |
| 4 | Damage classes to standardise? | **None.** A continuous *affected fraction* `b_aff_sf`/`bdg_sfc` ∈ [0.50, 1.0] — the "≥50% of footprint on the proxy" inclusion rule (min = 0.500). Same as OSU S1 → a single "likely damaged/destroyed" class → `damage_class = 2`. |
| 5 | Analysed-area layer? | **Yes** — one polygon, 32,712 km². |
| 6 | Does v2 envelop v1? | **100%.** The v2 AOI fully contains the v1 `analysed_extent` and is **4.2× larger** → clean supersede. |

### The "duplicate id" is a blank, not duplicate buildings

`id` has 68,005 unique values, but that hides one value — a single blank `' '` —
**shared by 13,433 rows**, all from the **"Venezuela (Bolivarian Republic)"
national footprint source** (their `bdg_id` is `noid_…`). Those are 13,433
*distinct* buildings (differing geometry/adm4) that simply lack an Overture GERS id.
`bdg_id` is unique across all 81,437, so **81,437 is a valid distinct-building
count** — not inflated (contrast the Microsoft cross-scene case, `exploratory/0001`).

### Consequence for harmonization: carry geometry, don't id-join

OSU (ADR-0009) attaches damage by an **id-join** onto our Overture base (99.4%
match). v2 can't reuse that cleanly:

- **13,433 buildings have a blank `id`** → un-joinable by id.
- v2 spans ~20 states but our Overture base only covers the quake-core ones
  (Carabobo, Miranda, La Guaira, Aragua, Distrito Capital, Yaracuy) at 100%; the rest
  (~30%, e.g. Lara, Sucre) are **0%** simply because we never pulled Overture there.

An id-join would silently drop ~25k buildings. Since v2 **carries the footprint
geometry itself**, the v2 silver should key on that geometry — self-sufficient over
the whole AOI, no Overture-base expansion needed.

### Data-quality note (not blocking)

`class`/`subtype` are garbled (asterisks / source-bleed) for ~13k rows. We don't use
those Overture-type fields, so it doesn't affect us — worth a mention to IMPACT.

## What this feeds

[ADR-0015](../../docs/decisions/0015-impact-v2-vector-damage.md): switch the
`impact_initiatives` source from the v1 raster proxy to the v2 vector product
(supersedes ADR-0008); harmonize by carrying v2 geometry; keep the amplitude-proxy
"wide-area screen, not confirmed damage" caveat.

## Reproduce

```sh
uv run --group etl python exploratory/0002-impact-v2-assessment/analysis.py
```
