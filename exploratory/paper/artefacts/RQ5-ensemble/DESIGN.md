# RQ5 — consensus ensemble: can multi-product agreement improve *building-level* damage mapping?

Status: **PROPOSED — awaiting sign-off before we compute.** (RQ0-style gate.)

## Question & scope

RQ2 showed every product is a high-recall / low-precision building mapper (precision 0.05–0.12,
over-detection 5–26×). RQ3 showed area *ranking* survives anyway. The remaining operational gap is
the **map itself**: can we flag the *right buildings* by counting only where products agree?

**Scope decision (user, 2026-07-07): classification only.** A rank-ensemble (combining per-cell
counts) would likely work but ranking is already good enough (RQ3a: top-20 ≈ 0.8 at res 7);
what needs improving is per-building mapping. Rank-ensemble parked as a possible extension.

## Why this can work, and the condition it depends on

A k-of-n vote keeps a TP if ≥k members caught it, and keeps an FP only if ≥k members made the
*same* mistake. The precision gain is large exactly to the degree member errors are **independent**.
RQ3b says errors are NOT independent (spatially structured, severity-aligned) — and IMPACT & OSU
share Sentinel-1 physics, so their FPs should co-occur far above chance. Hence the design
hypothesis, which is itself a finding:

> **H1 (sensor-pairing):** cross-sensor pairs (MS×IMPACT, MS×OSU) gain more precision per unit of
> recall lost than the same-sensor pair (IMPACT×OSU). The gap measures sensor-family error
> correlation.

> **H2 (frontier):** some voting rule strictly dominates every single product in precision at
> acceptable recall (the claim "ensemble improves the map" = a rule beating the best single
> product's F1, not merely raising precision — precision rises by construction).

## Construction basis vs scoring basis (the RQ0 tension, resolved)

- **Construction** (building the ensemble predictor): the **gold `building_flags` Overture base** —
  per-building flags `ms_dmg`, `sar_dmg` (IMPACT v2), `osu_dmg` (+ `uh_dmg`, see OQ4) already
  materialised per Overture id. Voting = boolean algebra on one table; nearly free. Using the
  viewer's snap here is fine: it defines the *predictor*, not the truth.
- **Scoring** (evaluating it): **identical dual-anchor harness as RQ2** (RQ0), vs native CEMS
  builtUpP points, r = 10 m primary / {5, 20} sensitivity. Each voting rule is a *synthetic
  product*: its damaged set = flagged Overture buildings (centroids), its analysed extent = the
  **intersection of member AOIs ∩ CEMS extent**. Recall anchored on CEMS points in that region;
  precision anchored on flagged buildings in that region.
- State in the paper: construction basis ≠ scoring basis; the ≤1 % MS snap loss (ADR-0017) applies
  to the predictor only. OSU/IMPACT are Overture-native anyway.

## Members & rules

Members (primary, per sign-off 2026-07-07): **MS, IMPACT v2, OSU, UH** — all four scored only
within `CEMS extent ∩ member AOIs` like everything else. UH's provider GeoJSON
(`final_maxsev_512.geojson`) landed in bronze and is harmonized to
`silver/source=uh/adm0=VE/footprints.parquet` (447,263 footprints incl. intact) with `uh_dmg`
in gold building_flags. UH has no provider AOI file → **derived**: union of H3 res-9 cells
(k=1 dilated) containing ≥1 UH footprint of any grade — "where it looked" is well-defined
because intact buildings are included. UH's sensor/modality is still unconfirmed (optical AI
assumed) — H1 pair-typing treats UH×SAR as cross-sensor provisionally.

Rules, each scored as its own synthetic product within ITS OWN member-AOI intersection:

| family | rules |
|---|---|
| singles (baselines) | MS, IMPACT, OSU, UH — re-scored *within the same quad-overlap region* so the frontier is apples-to-apples |
| pairwise AND | 6 pairs: cross-sensor (MS×SAR, UH×SAR, MS×UH) vs same-sensor (IMPACT∧OSU) → H1 |
| k-of-4 | 2-of-4, 3-of-4, 4-of-4 |
| union (1-of-4) | the "max recall / worst precision" endpoint anchoring the frontier |

Primary region = quad overlap (≈ Caraballeda — small but the only place all four looked).
Pairwise rules ALSO scored on their larger pairwise overlaps (coverage realism), flagged as
non-comparable to the quad-region numbers.

**Scoring-geometry caveat:** ensemble members are scored as Overture-building *centroids*
(building_flags has lon/lat, not footprints), so a large building whose CEMS point sits >r from
its centroid counts against recall — a construction-basis penalty that native-footprint RQ2
scoring didn't have. The singles are re-baselined identically, so the frontier is internally
consistent; the singles-vs-RQ2 delta quantifies the penalty explicitly.

**Deliverable fig:** precision–recall frontier (one point per rule + singles), r = 10 m, with
iso-F1 curves; plus the H1 bar (ΔP per ΔR by pair type).

## The consensus-as-evidence subsection (two-sided attribution, used constructively)

Per RQ2, "FP" conflates product error with CEMS under-enumeration. Consensus flips this into a
tool: buildings flagged by **all three independent-ish sensors but with no CEMS point within r**
are the strongest candidates for damage CEMS missed. Deliverable: count + map of high-consensus
non-CEMS buildings, reported as *candidate CEMS gaps* (NOT scored as TP — the scoring stays
conservative; this is a qualitative/forward-looking result, could seed a field-validation ask).

## Costs stated up front (paper honesty)

1. **Coverage:** consensus exists only on AOI intersections; triple ≈ Caraballeda only. Ensemble
   trades area for accuracy — report region areas alongside metrics.
2. **Latency:** ensemble availability = max(member latencies); tie to the §6 timeline
   ("consensus-as-of-day-X").
3. **Precision ceiling:** even a perfect ensemble is capped by CEMS point density (RQ2); report
   over-detection ratio alongside precision, as in RQ2.

## Decisions (signed off 2026-07-07)

1. **Members: all four (MS, IMPACT v2, OSU, UH)** — user: "include in all parts, but like the
   other 3 only include the area intersecting the CEMS coverage." UNEP stays excluded from voting
   (no AOI — "looked here" undefined).
2. **CEMS positives:** {Damaged, Destroyed} headline + "Possibly" sensitivity (RQ2 convention).
3. **Binary voting first**; grade-aware rules deferred to a second pass.
4. **Headline region: quad-overlap**; pairwise overlaps as robustness.
