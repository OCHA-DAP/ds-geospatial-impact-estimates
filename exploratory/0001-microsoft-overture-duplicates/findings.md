# Duplicate footprints in Microsoft's merged VE damage set — Microsoft or Overture?

> **Status:** complete & verified (2026-07-02).
> **Verdict: Microsoft cross-scene merge misses — not Overture.**
> Analysis: [`analysis.py`](analysis.py) · Feeds [ADR-0010](../../docs/decisions/0010-microsoft-merged-dataset.md).

## Question

ADR-0010 adopted Microsoft's single **merged, deduplicated** VE damage file on the
premise that it removes cross-tile double-counting. But the layer still shows many
near-duplicate footprints — same building, shifted a metre or two. Microsoft say
they build on **Overture** footprints, so: are these duplicates **introduced by
Microsoft** or **inherited from Overture**? And how many are there?

## Data

`bronze/source=microsoft/adm0=VE/merged/ALL_AOIS_building_predictions_deduplicated.gpkg`
— **72,162 footprints** (MultiPolygon, EPSG:32619), the exact file behind Microsoft's
published stats (72,162 analysed / 8,410 damaged). Columns include `id`, `orig_id`,
`source_file`, `sources`, `num_observations`, `damaged`.

## Findings

**The duplicates are Microsoft's own cross-scene detections that failed to merge —
Overture is not involved.** Microsoft ran the assessment over **5 satellite scenes**
(Planet / Vantor / BlackSky) that overlap spatially. A building in an overlap zone is
detected once per scene; Microsoft's merge collapses these *when the per-scene
footprints overlap enough*, but ~3,800 buildings whose footprints overlap too little
slip through and remain as separate rows.

### The chain of evidence

| # | Check | Result |
|---|---|---|
| 1 | Is a building **id** duplicated? | `id` 100% unique. `orig_id` repeats, **but…** |
| 2 | …is `orig_id` a building id? | No — rows sharing an `orig_id` are a **median 5.7 km apart** (p99 16 km). It's a colliding tile-local id. **Red herring.** |
| 3 | Exact-duplicate **geometry**? | **0** — every copy is jittered, never identical. |
| 4 | **Spatial** near-dup clusters | ~3,600–4,400 buildings appear as 2–4 footprints (details below). |
| 5 | Are they the **same building**? | 97% of pairs are **mutual nearest neighbours**; 98% of clusters have **one footprint per distinct scene**. |
| 6 | Microsoft's own metadata | `num_observations` == #scenes in `sources` (100% consistent). The duplicates carry `num_observations = 1` (100%) and are **disjoint** from the correctly-merged set. |

### Scale — and impact on Microsoft's published numbers

Clustering the cross-scene duplicates (close centroid + similar area + different
scene), across two threshold choices:

| Criterion | Unique buildings (vs **72,162**) | Inflation | Unique damaged (vs **8,410**) | Inflation |
|---|---|---|---|---|
| tight (≤3 m, area ≥0.7) | ~68,175 | **~5.5%** | ~8,323 | ~1.0% |
| looser (≤5 m, area ≥0.6) | ~67,808 | **~6.0%** | ~8,234 | ~2.1% |

- **"72,162 buildings analysed" is inflated ~5–6%** (~3,600–4,400 counted 2–4×);
  true unique ≈ **68k**.
- **"8,410 damaged" is barely affected (~1–2%)** — damaged buildings are mostly in
  scene interiors, and where duplicated the scenes usually *disagree*, so an
  any-scene-damaged collapse counts them once anyway.
- **~900 duplicated buildings get conflicting damage calls** across the two scenes
  (damaged in one, not the other) — a reconciliation signal, not a counting bug.

### Why the merge misses them (the mechanism)

The un-merged duplicate footprints **never overlap by more than IoU ≈ 0.5** — a hard
ceiling. That is exactly the signature of a merge threshold: Microsoft merge
cross-scene detections above ~0.5 IoU (→ one row, `num_observations` = #scenes), and
anything below survives as separate rows (`num_observations = 1`). The two
populations are disjoint (25,094 merged vs 7,788 duplicate rows, 6 in both), so a
building is either merged *or* duplicated, essentially never both.

### Why not Overture

The per-scene footprints of one building **differ geometrically** (that's why they
don't merge). If Microsoft simply reused a single Overture footprint per scene, the
copies would be identical and would merge trivially. The variance is between
Microsoft's own per-scene detections, so the duplication is a Microsoft
detection/merge artifact — Overture (their input source) does not produce it. An
earlier Overture cross-check agreed: near-dup pairs mapped to a *single* Overture
building with no conflation signature.

## What this feeds

- **No fix on our side.** Our reference footprint base is Overture, which this does
  not touch; the Microsoft layer is a comparison source. Not worth deduping in
  `harmonize_microsoft.py`.
- **Flag to Microsoft.** Their headline "buildings analysed" is ~5–6% high due to
  ~3,800 un-merged cross-scene re-detections (all `num_observations = 1`); damaged is
  fine; ~900 buildings carry conflicting cross-scene damage calls.
- **ADR-0010** gets a one-line note: the merged set is *mostly* deduplicated, with a
  quantified residual of cross-scene misses that we accept (does not affect the
  Overture-based comparison).

## Reproduce

```sh
uv run --group etl --with scipy python exploratory/0001-microsoft-overture-duplicates/analysis.py
```
