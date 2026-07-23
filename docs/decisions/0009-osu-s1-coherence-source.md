---
status: "accepted"
date: 2026-06-29
deciders: tdowning
---

# Adding the OSU Sentinel-1 coherence damage assessment as a fourth source

## Context and Problem Statement

Oregon State University (Corey Scher & Jamon Van Den Hoek) produced a preliminary
Sentinel-1 *coherent change detection* building-damage assessment for the 24 June
2026 Venezuela earthquake (USGS `us6000t7zp`; Copernicus EMS activation
`EMSR884`), distributed via NASA Disasters and a Box package. Unlike the IMPACT
raster proxy (ADR-0008), the delivery is already a per-building vector product
**keyed to Overture footprints** (`overture_id`), plus a delivered analyzed-area
polygon. How do we standardise it into the common model and surface it like the
other sources?

## Decision Drivers

* Keep one comparable data model across sources (Microsoft, Copernicus EMS, IMPACT
  SAR, this).
* Reuse the existing per-source machinery (silver `building_damage` +
  `analysed_extent` → `SOURCES` in `harmonize_common`) rather than inventing new.
* Be honest about what it is — preliminary, unvalidated; an indicator, not a
  building-by-building census.
* Don't break the (currently untiled) browser agreement view at millions of points.
* It is a genuinely *independent* SAR method (coherence loss vs IMPACT's amplitude
  z-score) and is ShakeMap-calibrated — worth surfacing distinctly.

## Considered Options

* **Project by geometry** (spatial intersect onto the Overture base, as Microsoft
  and the IMPACT raster do).
* **Project by id** (join the delivery's `overture_id` straight onto our base).

## Decision Outcome

1. **Join by `overture_id`, not geometry.** The source is built on Overture, so the
   damaged set is a straight id-join onto our base (99.4% match) — no raster
   sampling, no spatial intersect. The ~0.6% of damaged ids absent from our base
   (a slightly different Overture vintage) are dropped, consistent with how every
   source handles base mismatches.
2. **Single `damage_class` 2 (Damaged); `damage_probability` carried as confidence.**
   The product is a binary "likely damaged/destroyed" flag, not a graded severity;
   we map it to class 2 on the xBD/CEMS scale rather than inventing
   possibly/destroyed splits. The model score rides along as the confidence signal
   (cf. SAR's `sar_z`).
3. **Analysed extent = the delivered analyzed-area polygon.** Unlike IMPACT (whose
   masked raster forced "footprint = raster bounds"), OSU ships an explicit
   coverage layer; base buildings within it are OSU-analysed. This gives an honest
   ~77% coverage at adm0 (the delivery reports ~75% of dry land imaged).
4. **TEMPORARY — per-building projection is damaged-only.** As with SAR (ADR-0008),
   only OSU-*damaged* buildings enter the per-building `building_flags` layer; the
   full ~2.1M analysed set is not materialised there. Admin-level facts (exposed /
   analysed / damaged / coverage) are still computed from the base, so aggregate
   numbers are complete.

### Consequences

* Good: the cleanest source integration to date — an id-join plus one coverage
  polygon, no new machinery; the viewer lists it with the same coverage-aware
  hover metrics and no per-source frontend logic.
* Good: a second, *methodologically independent* SAR signal (coherence, and
  ShakeMap-calibrated to ≤1% false alarm in lightly-shaken areas) — a natural
  cross-validation reference for the IMPACT proxy and the optical sources.
* **Bad / temporary:** the building-level agreement layer under-represents OSU
  (damaged-only), the same stopgap as SAR. **MUST be rectified when PMTiles /
  vector tiling lands** — marked `# TEMPORARY` in `harmonize_common`.
* Neutral: bound to the delivered Overture vintage; a re-keyed delivery would shift
  the ~0.6% unmatched set.

## Pros and Cons of the Options

### Project by id (`overture_id`)

* Good, because exact and cheap — no geometry scan over millions of footprints.
* Good, because it preserves the producer's own building↔damage assignment.
* Bad, because it depends on Overture-vintage alignment (mitigated: 99.4% match).

### Project by geometry

* Good, because vintage-independent (matches whatever our base holds).
* Bad, because it discards the producer's exact assignment and re-derives it via
  intersect, adding edge-effect error for no benefit when ids are already present.

## More Information

Method: Sentinel-1 coherent change detection — coherence loss between two
post-event passes (24 Jun 22:50 UTC, 25 Jun 10:16 UTC) and a 1-year pre-event
reference stack; a building is flagged when ≥50% of its footprint falls on the
coherence-loss map. The threshold is calibrated against the USGS ShakeMap field
(false alarm ≤1% in lightly-shaken areas); 30 m; preliminary, unvalidated. Cite as
*Damage analysis of Copernicus Sentinel-1 data by Corey Scher and Jamon Van Den
Hoek of Oregon State University* (delivery README in
`bronze/source=osu/adm0=VE/README.md`).

Revisit (1) the damaged-only stopgap with the tiling work (ADR-0008), and (2) a
formal cross-validation of OSU coherence vs the IMPACT amplitude proxy and the
optical sources where their extents overlap.

## Amendment — v1 delivery (2026-07-22)

OSU published a **v1** on HDX (01 Jul 2026 pass): coverage expanded so the USGS
ShakeMap MMI>=VI strong-shaking zone is 100% imaged, monitored footprints grew
2,133,587 -> 2,699,969 (+26.5%), and the headline is **69,431 likely damaged**
(was 58,870). Three schema/assumption changes vs v0, and the decisions taken:

1. **Continuous `damage_probability` -> categorical `damage_confidence`.** v1
   grades certainty in three ordinal tiers — `possible` / `probable` /
   `high_confidence`. We carry the tier as OSU's native confidence signal (it
   replaces `damage_probability`; the native popup shows whichever field the tile
   has). Confidence is *certainty, not severity*: every damaged building stays
   `damage_class 2` — we do **not** promote `high_confidence` to Destroyed. (OSU
   is the only source giving clean ordinal certainty; a normalized cross-source
   confidence dimension is deferred to its own ADR.)

2. **The gpkg now bundles non-damaged rows.** `damage==1` (probable +
   high_confidence) = 69,431 = the published headline; `possible` (54,202,
   `damage==0`) is a lower-confidence *candidate* tier. The damaged files
   (`building_damage`, `damage_footprints`) filter to `damage==1` so the common
   model / native view are unchanged in meaning. `possible` is kept **only** in a
   new silver `assessed_confidence.parquet` (the full tiered set) for downstream
   analysis — never injected into the common-model gold, which is a damage fact
   table (that would reopen the deferred damaged-only stopgap for no gain).

3. **Versioned silver, single published version.** Because we have a near-term
   need to *compare* v0 vs v1, both are materialised side by side under
   `silver/source=osu/adm0=VE/version={v0,v1}/`. `ingest_osu.py` / `harmonize_osu.py`
   take `--version` (default v1); v0 logic is preserved verbatim. Downstream
   (`harmonize_common`, `build_platinum`) reads exactly one via
   `gie.config.OSU_PUBLISHED_VERSION` — rollback = flip that constant and rebuild.
   Gold and platinum are **not** version-partitioned (the common model is a merged
   all-source table; per-source versioning there is meaningless, and platinum is
   cheap to rebuild — the staging->promote gate is the live rollback). Bronze keeps
   both deliveries permanently (filenames carry the version).

Rejected: version-partitioning gold/platinum (materialising history at derived,
rebuildable layers — reproducibility beats retention); mapping the confidence
tiers to severity classes (conflates certainty with severity). v1 also ships
`EMSR884_adm2_damage_pct` (the provider's own adm2 rollup) — retained in bronze as
a validation cross-check, not ingested as a pipeline source.
