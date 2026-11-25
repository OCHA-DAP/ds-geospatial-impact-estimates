# 0004 — Validating the v2 containment rule for the id-less UH footprints

**Date:** 2026-07-06
**Question:** UH damage predictions are graded footprints that *look* like our
Overture base (~80% IoU≥0.95 in a Caraballeda bbox, per the ingest interrogation)
but carry **no feature id**. `harmonize_common` therefore projects a damaged/
destroyed UH footprint onto the base by **centroid-containment** — a base building
is flagged when it `ST_Contains` the footprint's `ST_PointOnSurface` (the impact_v2
rule, [ADR-0015](../../docs/decisions/0015-impact-v2-vector-damage.md)). Does that
rule map cleanly, or does it drop / merge footprints?

## Method

`analysis.py`: dedup the Overture VE base by id; take the 80,913 UH footprints
graded damaged/destroyed; `LEFT JOIN` each footprint's point-on-surface to the base
building that contains it. Per AOI, count:

* **native** — UH damaged/destroyed footprints (distinct, = the source's own count)
* **matched** — of those, how many land inside *some* base building (an Overture
  twin exists) → match rate
* **projected** — distinct base buildings flagged = what the pipeline reports on the
  Overture base
* **collapse** — `matched − projected`: footprints sharing one base building (UH
  finer than Overture)

## Findings

```
aoi           native  matched  projected  match_rate  collapse
Antimano       6301    5901     5566       93.7%       335
Caraballeda    6138    5780     5518       94.2%       262
Caracas       22139   21331    20086       96.4%      1245
Maracay        9703    9703     9111      100.0%       592
Moron           474     474      450      100.0%        24
Petare           40      39       39       97.5%         0
Santa Cruz    34343   34343    32326      100.0%      2017
Villa de Cura  1775    1775     1684      100.0%        91
TOTAL  native=80,913  matched=79,346 (98.06%)  projected=74,780  collapse=4,566  unmatched=1,567
base buildings holding >1 UH damaged footprint: 4,353 (max 12 per base)
```

1. **The rule is correct** — 98.06% of UH damaged footprints have an Overture twin
   containing their point-on-surface. No geometry sampling, no id needed.
2. **UH is NOT Overture-identical at full scale.** The 80% IoU figure was a single
   Caraballeda bbox; across the eight AOIs, two effects appear:
   * **1.94% unmatched (1,567)** — UH footprints with *no* Overture twin, so
     containment drops them. Concentrated in the greater-Caracas AOIs (Antimano
     93.7%, Caraballeda 94.2%, Caracas 96.4%) — informal structures Overture lacks.
     The four Aragua/Carabobo AOIs (Maracay, Moron, Santa Cruz, Villa de Cura) match
     100%.
   * **5.6% collapse (4,566)** — several UH footprints falling in one Overture
     building (up to **12:1**), heaviest in the dense barrios (Santa Cruz 2,017,
     Caracas 1,245) *even where the match rate is 100%*. UH's footprints are finer
     than Overture there.
3. **Net:** native **80,913** → Overture-**projected 74,780** (**−7.6%** =
   1,567 dropped + 4,566 merged).

## Follow-up (2026-07-07): duplicates inflated the native side

This ran on the raw delivery. It was later found that the GeoJSON has **~13% exact-
duplicate footprints** (61,195 rows), **5,644 with conflicting grades** (same building
tagged intact AND damaged). Silver now dedups exact geometries worst-grade-wins
(478,467 → 447,263; damaged/destroyed 80,913 → **76,378**). So the "native 80,913" and
"collapse 4,566" here were partly duplicate damaged footprints. The Overture-projected
count (~74,700) is unchanged (it already collapsed duplicates onto one base), so the
**true native↔projected gap is ~2%, not −7.6%** — the −7.6% was mostly the duplicates.
The match-rate conclusion (the containment rule is clean) stands.

## What it feeds

* **The decision holds.** Containment is the right projection: snap (the debris
  rule) would collapse the finer footprints identically *and* mis-attach the 1,567
  twinless ones to a nearest neighbour. Dropping the twinless footprints is the
  conservative, honest choice for an Overture-based count.
* **Report UH on two bases** ([ADR-0017](../../docs/decisions/0017-source-counts-two-bases-snapped-vs-native.md)):
  the common-model / cross-source count is the Overture-projected **74,780**; the
  source's **native 80,913** is carried separately (native tiles). The −7.6% gap is
  the same phenomenon as UNEP debris, but far milder (debris was −21%).
* Justifies [ADR-0018](../../docs/decisions/0018-uh-damage-prediction-source.md).

Reproduce: `GIE_BLOB_ACCOUNT_PREFIX=imb0chd0 uv run --group etl python exploratory/0004-uh-containment-validation/analysis.py`
