# Scaling the melt-precursor watch: design brainstorm

Status: **brainstorm**, written 2026-08-30 alongside exploratory 0005. Not a
commitment — a design sketch for what a global (HMA-first) monitoring system
built on the 0005 detector would look like, and the gate it must pass first.

## 0. What 0005 actually established (and the design constraints it sets)

- A face-scale (~6 km²) morning-pass backscatter anomaly, referenced to its own
  multi-year day-of-year climatology and a regional control, caught the Langtang
  collapse 8 weeks out (stat −3.05) with a 1.3 %/face-season false-alarm rate
  over 226 face-seasons.
- **Whole-glacier AOIs kill the signal** (source glacier polygon: −1.5, missed).
  The unit of analysis is the face, not the glacier.
- The offset-tracking null says motion methods add nothing early for this
  failure type; they belong in the *escalation* tier, not the screening tier.
- This is one positive control. Everything below is provisional until the
  historical replay (§6) runs.

## 1. Unit of analysis: fixed steep-ice facets, not glacier polygons

Call: **DEM-derived facets, ~1–2 km², built once and versioned.** Recipe: RGI7
ice mask (+200 m buffer for headwalls above ice) ∩ GLO30 slope ≥ 25° ∩ elevation
above the regional late-summer snowline; split the resulting mask by dominant
aspect octant; enforce 0.5–4 km² per facet by merging/splitting. Aspect-splitting
matters because the detector's physics is thermal — a north face and a south
face on one glacier are different instruments.

Reject: per-glacier polygons (dilution, proven) and naive square grids (a tile
straddling two aspects blurs the refreeze signal; acceptable fallback for the
MVP if facet code is a time sink).

Counts, order of magnitude: HMA has ~98k RGI glaciers; steep-ice facets land
around **30–80k units for HMA** and **150–400k globally**. Treat 10⁵ as the
design number.

## 2. Compute architecture: GEE for pilot, RTC-on-cloud for operations

The data product per unit is tiny — mean VV/VH dB per facet × orbit ×
acquisition. The cost is reading S1 GRD.

- **Pilot (through one live season): stay GEE-native.** 0005's per-orbit
  reducers already work; scale by mapping `reduceRegions` over facet
  FeatureCollections per new scene, exporting rows to BigQuery/GCS. HMA sees
  ~10–30 relevant scenes/day; trivial batch load. Known frictions from 0005:
  "too many concurrent aggregations" (chunk it) and GEE's commercial-use
  licensing — fine for a pilot, murky for an operational UN system.
- **Operational: migrate to Sentinel-1 RTC** (Microsoft Planetary Computer /
  AWS) with a small per-scene serverless reducer. RTC (radiometrically
  terrain-corrected γ⁰) directly attacks the biggest physical weakness —
  radiometry on 40° slopes — and removes the licensing question. Compute stays
  small: low hundreds of $/month globally; the engineering cost is the stack,
  not the cycles.
- **Baselines:** per facet × orbit × 15-day DOY bin, stored as parquet (a few
  GB globally), rebuilt annually with the newest year folded in and the tested
  year always excluded at evaluation time (leave-one-out semantics, as in 0005).

Incremental evaluation per scene: reduce intersecting facets, append,
re-evaluate detector — seconds of work, so the system is near-real-time by
construction (latency = S1 publication lag, hours).

## 3. Statistics at scale: rank, don't page

10⁵ facets × 1.3 %/season ≈ **thousands of alarms/season**. A pager fires
itself into being ignored. Calls:

- **The product is a continuously ranked watch-list** (a "glacier fire-danger
  index"), not a binary alert stream. Tiers on top of the ranking:
  - *Watch*: ≤ −2σ sustained 3 weeks (define persistence in **days, not
    acquisition counts** — repeat interval will keep changing as S1C/D densify;
    0005's "3 consecutive" at 12-day spacing ≈ 5 weeks).
  - *Elevated*: ≤ −3σ sustained, **plus** the asc/desc asymmetry check (morning
    anomalous, evening normal — 0005's physical signature, cheap to automate,
    and it discriminates "sick face" from "sensor/weather artefact").
  - *Critical*: elevated + ≥ 4 weeks persistence + human review. Langtang's
    −3.05 clears this tier.
- **Regional adjustment:** fleet-median works only in a homogeneous fleet.
  Replace with a hierarchical control: median z of facets in the same orbit ×
  elevation band (±300 m) × aspect class within ~100 km; fall back to wider
  radii when membership < ~20. This is the single most important piece of
  statistical engineering — it is what keeps a warm summer from lighting up an
  entire mountain range.
- **Validation set (S1 era only):** Kolka 2002 and Flat Creek are pre-S1 —
  unusable. Usable positive controls: **Aru Co (Jul + Sep 2016**, sparse
  early-S1 coverage but present), **Sedongpu basin (2017–2018 sequence)**,
  **Marmolada (Jul 2022**, heatwave-driven — the best analogue), and
  **Chamoli (Feb 2021)** — which the detector should be *predicted to miss*: a
  winter rock/ice failure with no melt-loading signature. Include it anyway: a
  monitoring system must state what it cannot see, and Chamoli defines that
  boundary.

## 4. Escalation chain and the ethics of an experimental warning

When a facet reaches *elevated*: automatically generate the second-look bundle
(asc/desc asymmetry panel, neighbour-control divergence, offset tracking —
useful only as a late-stage/negative check per 0005 — and InSAR coherence where
the surface is dry). At *critical*: human glaciologist review, then Planet/Maxar
tasking.

**Nothing leaves the system without a human.** Downstream consumers are
specialist intermediaries, not the public: ICIMOD and national agencies (DHM
Nepal, CWC India) in HMA, GAPHAZ as the scientific clearing-house, OCHA
internally as situational awareness feeding preparedness — never a public
warning. The live Tibet-side −7.5σ face is the test case of the ethics: it sits
in another jurisdiction, from an unvalidated system, yet silence has its own
cost. The answer is a **pre-agreed notification protocol** written before
operations start: what tier triggers notification, to which named authority,
with what mandatory caveats, logged. Improvising this per-event is how
experimental systems either cause panics or get quietly shelved. Framing
discipline: this is a *reconnaissance-prioritisation tool* until it has survived
at least one prospective season; the word "warning" is earned, not declared.

False-alarm cost is not symmetric with miss cost, but it is not zero:
evacuations, closed valleys, cried-wolf erosion. The tier system exists to spend
human attention, not to trigger action directly.

## 5. Failure modes (ranked)

1. **Non-stationarity:** under sustained warming, every facet drifts negative
   against a fixed climatology and the alarm rate ratchets up. Use rolling
   5–6-year baselines and monitor the fleet-wide z distribution as a system
   health metric.
2. **Where the physics doesn't hold:** the 6 am/6 pm logic travels well in
   *time* (S1 is sun-synchronous, ~06:00/18:00 local everywhere) but the
   nocturnal-refreeze contrast fails in polar summer (no night), on maritime
   glaciers that are wet all season (Alaska coast, Patagonia, NZ — detector
   degrades to a plain anomaly index), and for dry-season failures (Chamoli
   class — out of scope, say so loudly).
3. **Platform/radiometric heterogeneity:** S1A/C/D mixing within an orbit (0005
   mixed A+D silently); fit per-platform bias terms or keep per-platform
   climatologies; watch for processor-version steps in the archive.
4. **Coverage asymmetry:** some facets lack a descending (morning) pass
   entirely; they get a degraded single-geometry score, flagged as such — never
   silently blended.
5. **Snowline/AOI drift:** a facet whose lower half leaves the snow zone changes
   its own statistics; version the facet layer and re-baseline on updates.

## 6. Roadmap (and the gate before any building)

- **Phase 0 — historical replay (2–4 weeks, one person, GEE + existing 0005
  code):** run the detector over Aru, Sedongpu, Marmolada, Chamoli plus a
  ~5,000-facet HMA backtest 2017–2026. Deliverable: a real ROC and the honest
  scope statement. **Gate: catches ≥ 2 of the 3 melt-driven positives at a
  tolerable rate — otherwise stop, publish the negative result, and this
  document is void.**
- **Phase 1 — HMA MVP (4–8 weeks):** facet layer for HMA, nightly GEE ingest,
  ranked watch-list dashboard, internal only.
- **Phase 2 — one prospective season with partners (ICIMOD/DHM):** live ranking,
  tasked second looks, notification protocol drafted and signed, post-season
  skill report.
- **Phase 3 — global + RTC migration + governance**, only if Phase 2 shows
  skill.

Effort through Phase 2: roughly one engineer plus a part-time glaciologist. The
immediate next step is unambiguous: **Phase 0 before any infrastructure** —
the historical events are sitting in the archive, and they will tell us in a
month whether this system deserves to exist.

## Open questions

Facet-level false-alarm rate (0005 measured glacier-level; expect worse); VH's
added value (unexamined); whether the fleet-median generalises to heterogeneous
fleets (the hierarchical control is a design guess); detector behaviour in the
2015–2016 sparse-coverage era that two validation events sit in.
