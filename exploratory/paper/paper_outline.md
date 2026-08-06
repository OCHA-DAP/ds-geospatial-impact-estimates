# Paper outline — draft v0.1

> Working document. Inline **[DECISION]** callouts mark choices to settle before we
> implement. Nothing here is committed prose yet.

---

## Title / Objective

**Working title (author's):** *Evaluation of near-realtime damage analysis products in the
Venezuela earthquake response.*

**Alternatives to consider:**
- *From orbit to operations: benchmarking rapid satellite damage products against Copernicus
  EMS in the 2026 Venezuela earthquake.*
- *Fast, accurate, available — pick two? A humanitarian evaluation of rapid damage-assessment
  products for the 2026 Venezuela (M7.5) earthquake.*

**Objective.** Evaluate the operational usefulness of the rapid satellite-derived building-damage
products that were produced for the June 2026 Venezuela earthquake, judged on three axes a
humanitarian responder actually cares about:
1. **Availability** — did it exist, could we legally use it, in what format/access.
2. **Latency** — how long after the event was it usable.
3. **Performance**, split into two distinct questions:
   - **3a. Classification accuracy** — does it label the *right buildings* as damaged
     (precision / recall / F1 vs ground truth).
   - **3b. Prioritization skill** — does it rank *areas* (admin / hex units) in the right order
     for triage, *even if* its per-building labels are noisy.

**Ground truth.** Copernicus EMS (CEMS) Rapid Mapping activation **EMSR884**, the per-building
point/area damage grading, is the ground truth. This is a deliberate, defensible choice, not a
convenience: CEMS is **trained-analyst visual interpretation of very-high-resolution imagery** — a
human directly *observing* structural damage (collapse, roof loss, debris), not an algorithm
inferring it. Within the area it analysed it is reference-grade, which is precisely why the
automated damage-assessment field trains and validates *against* CEMS/UNOSAT grades. Its scope is
bounded in two well-defined ways that we handle explicitly, and neither is a question of accuracy:
(i) **coverage** — it is truth only inside its `analysed_extent`; (ii) **visibility** — nadir VHR
optical resolves structural/roof collapse extremely well but not a narrow class of damage invisible
from directly above (e.g. soft-story collapse with roof intact), which matters only when
*interpreting SAR disagreements* (§4.4b), never as a claim that CEMS mislabels what it can see.

**Central thesis (the reason 3a and 3b are separate).** The operationally interesting question is
*not* "which product is most accurate" but **"can a fast, large-area, high-false-positive product
still direct response correctly?"** These automated products (SAR, optical ML) cover huge areas
within hours-to-days; CEMS is expert manual interpretation that is slower and spatially limited.
A product can be a *poor classifier yet an excellent prioritizer* — **if, and only if, its errors
are spatially unbiased.** A uniformly-inflated false-positive rate preserves the ranking of
worst-hit areas (everything is over-counted equally); a *spatially structured* false-positive rate
corrupts it and misdirects response. So the headline number is not the FP rate — it is whether the
error is **noise or bias**. Establishing that a noisy-but-unbiased product is a valid
"where-to-look-first" layer that front-runs CEMS by days is the paper's core contribution.

> **Motivating observation.** An external group reported a high false-positive rate for the
> **Microsoft** product within a specific sub-region. If real and *localized*, that is exactly the
> spatially-structured error that would break prioritization — so we treat it as a named
> investigation (§4.5 / §6.6): reproduce it against CEMS, localize it, and test whether Microsoft's
> area-ranking survives despite it. We expect several sources to show elevated FP rates; the value
> question is whether their prioritization holds regardless.

> **[RESOLVED] CEMS is ground truth.** CEMS Rapid Mapping is *trained-analyst visual
> interpretation of VHR imagery* — direct human observation of structural damage, categorically
> different from the algorithmic products it grades. Within its analysed extent it is reference-
> grade, and it is the accepted training/validation standard for the whole automated damage field.
> We call it **ground truth** (not "reference standard"). The two bounds — coverage and
> visibility — are handled explicitly (see the Ground-truth paragraph above) and are *not*
> accuracy caveats. Do **not** hedge CEMS as merely "a reference"; the defensible strong claim is
> the correct one and it makes the FP/bias analysis (§4.4) cleaner — errors against CEMS are
> genuine errors, not artefacts of comparing two noisy products.

---

## 1. Introduction & motivation

- The recurring humanitarian problem: in the first hours-to-days after a major earthquake,
  responders need *where is the damage and how bad* before field access is possible. Satellite
  damage products fill that window.
- The supply side has exploded: government/agency rapid-mapping (CEMS), SAR-based proxies
  (IMPACT, OSU/NASA), optical ML footprint-damage (Microsoft), crowd/AI hybrids (HOT fAIr),
  debris-mass modelling (UNEP/OCHA JEU), commercial/licensed inference (DISHA/UNOPS).
- They differ in sensor, method, unit of analysis, class scheme, coverage, latency, and licence —
  yet responders must choose among them in real time with little basis for comparison.
- **Contribution.** A single-event, apples-to-apples benchmark of *all* products that were
  actually produced for one event, on the three operational axes above, with a reproducible
  harmonization + scoring pipeline. Not a method paper — an *operational utility* paper.
- **Why this event.** The 2026 Venezuela M7.5 (USGS `us6000t7zp`, near Yumare; damage concentrated
  in the La Guaira / Caraballeda / Catia La Mar coastal strip NW of Caracas) drew an unusually
  dense set of independent products over ~1 week — a natural experiment.

> **[DECISION] scope: one event or a template.** Recommend we write this as a single-event case
> study but structure the methods as a *reusable evaluation framework* (so the next activation can
> be run through it). Cheap to do, materially raises the paper's value. Agree?

---

## 2. Background & event context

- **2.1 The event.** M7.5 (and M7.2 foreshock, `us6000t7zc`), date/time, epicentre, depth, USGS
  ShakeMap intensity (MMI contours), exposed population/settlement. Map: epicentre + MMI + the
  affected coastal municipalities.
- **2.2 The response.** Who activated what (CEMS activation trigger + date), which actors stood up
  which products, the information environment responders faced.
- **2.3 The damage-product landscape (conceptual).** A short taxonomy: sensor family
  (SAR vs optical), method (change-detection / coherence / amplitude proxy / optical ML /
  debris model / expert interpretation), and output unit (footprint / point / block / raster /
  mass). Sets up the harmonization problem in §4.

---

## 3. Products evaluated (the data)

One subsection per product; each states **method, sensor, unit, class scheme, spatial coverage,
licence, and our ingestion date**. Master comparison table below (the paper's Table 1).

| Product | Provider | Sensor / method | Native unit | Classes | Analysed AOI? | Licence | Our ingest |
|---|---|---|---|---|---|---|---|
| **CEMS EMSR884** (ref) | Copernicus EMS | VHR optical, expert interpretation | Points (builtUpP) + blocks (builtUpA) | Graded (destroyed→possibly) | Yes (analysed_extent) | Open (CEMS) | 2026-06-27→07-02 |
| **IMPACT v2** | IMPACT Initiatives | Sentinel-1 SAR amplitude proxy | Overture footprints | Binary damaged | Yes (S1 swath AOI) | — | 2026-07-02 (v1 raster 06-28) |
| **OSU / NASA** | Ohio State / NASA | Sentinel-1 coherence change | Overture footprints | Binary (+ probability) | Yes (analyzed-area) | Open (cite) | 2026-06-29 |
| **Microsoft** | Microsoft (via HDX) | Optical ML footprint damage | Footprints | Binary damaged | Valid-area mask (no true AOI) | CC-BY | 2026-06-26→29 |
| **HOT fAIr** | HOT (via HDX) | AI + crowd optical | Points | Graded (destroyed/major/minor) | **No** (detected-only) | CC-BY | 2026-06-29 |
| **UNEP/OCHA JEU** | UNEP JEU (via HDX) | Debris-mass model | Footprints + grids | **Mass (tonnes)**, not a grade | **No** (detected-only) | HDX | 2026-07-01→03 |
| **DISHA** | UNOPS | ML inference on Open Buildings | Footprints (points) | Binary damaged | Yes (NW Caracas AOI) | **Restricted** (no public redistribution) | 2026-07-02 |
| *USGS ShakeMap* | USGS | Seismic model | Contours | Intensity (MMI) | n/a | Open | 2026-07-01 |

Notes the table must carry:
- **DISHA licence.** UNOPS non-commercial; no public display/derivative/redistribution without
  written authorization. This is an *availability* finding in its own right (§6.1), and constrains
  what we can publish — figures using DISHA may need aggregation/embargo.
- **UNEP debris** measures *mass*, not damage grade — it is not directly comparable in a
  confusion matrix. Treated as a supplementary/qualitative layer (or via a mass↔damaged proxy we
  define explicitly). **[DECISION]** include UNEP in the quantitative comparison at all, or keep
  it qualitative?
- **USGS** is seismological context, not an analytic damage product — used as an exposure/intensity
  covariate, not scored.
- **IMPACT v1 (raster proxy)** was the *first* usable damage signal (06-28) and was later
  superseded by v2 (vector, 07-02). Latency and accuracy differ between v1 and v2 — recommend we
  report **both** (v1 = "what responders had on day 3", v2 = "the corrected product"). This is one
  of the paper's sharper latency-vs-accuracy stories.

---

## 4. Methods

### 4.1 Timeline / latency reconstruction
- **Sources of truth for timing:** (a) the auto-maintained ingestion ledger (`data_ledger.md`,
  `src/gie/ledger.py`) — day-granularity of when *we* received each product; (b) git commit
  history of the ledger/loaders — finer-grained ingestion timestamps; (c) product internal dates
  (acquisition date, activation date, delivery README/transmittal); (d) **provider confirmation**
  — email/HDX release timestamps to convert *our-ingest* latency into *true-release* latency.
- **Metric:** hours/days from event origin time (USGS) to (i) provider release and (ii) our
  operational availability. Report both; be explicit that our-ingest is an upper bound on
  provider-release.
- Deliverable: a release-timeline figure (event → each product's first availability → updates).

> **[DECISION] latency zero-point.** Event origin time, or the CEMS activation time, or "first
> responder request"? Recommend **event origin time (USGS)** as the clock zero — cleanest, most
> comparable across events.
> **[DECISION] how hard do we chase provider dates?** Ledger+git gets us our-ingest for free;
> true-release needs outreach. Propose: publish our-ingest now, footnote which providers we've
> confirmed, upgrade as replies arrive.

### 4.2 Matching CEMS to each product (design in `artefacts/RQ0-matching-basis/DESIGN.md`)
- **We do NOT score against the viewer's gold `facts.parquet`.** It snaps *CEMS itself* onto the
  Overture base (2.6% of `builtUpP` points drop, 12% collapse), conflates detection error with
  footprint-granularity collapse (ADR-0017), explodes coarse blocks into fabricated per-building
  labels, and contains modeled `damaged_extrapolated` damage. It is a comparison *visualisation*,
  not a validation dataset — reported only as the *operational* baseline. Paper numbers come from a
  purpose-built match on the immutable **silver** snapshots.
- **Primary method — dual-anchored pairwise *native* matching.** CEMS stays native (bare
  points/blocks); each product keeps its own footprints (Overture for OSU/IMPACT — genuinely their
  base, not a snap; MS's own; UNEP's GBA). Precision and recall are computed from **opposite
  anchors**, so no shared building universe or true-negative count is needed:
  *recall* = fraction of CEMS damage points with a product-flagged building within radius *r*;
  *precision* = fraction of product-flagged buildings with a CEMS point within *r*. F1 from the two.
- **Match radius r = 10 m primary, {5, 20} m sensitivity**, drop/collapse rates reported. Chosen,
  not inherited from the viewer's 20 m.
- **The one assumption** (licensed by CEMS-as-ground-truth): within CEMS's analysed extent, a
  building with no CEMS feature nearby is genuinely undamaged → a product flag there is a true FP.
- **Coverage-awareness is mandatory & per-pair:** all scoring confined to the **intersection of the
  product's and CEMS's analysed extents**; never score `damaged_extrapolated`. Detected-only
  products (UNEP) have no AOI → handled by the enclosed-admin assumption (§RQ4 / §4.3).
- **Class harmonization:** binary primary (headline {Damaged, Destroyed} = positive; "Possibly
  damaged" reported both in and out — see decision below), ordinal secondary where both sides grade.

> **[RESOLVED → confirm] matching design.** Chose dual-anchor pairwise-native over a shared-Overture
> confusion matrix: it isolates detection skill from footprint granularity, keeps the reference
> undistorted, and treats all sources uniformly despite heterogeneous keys. Cost: no TN-based
> metrics (specificity/accuracy), which rare-event detection doesn't want anyway. **Two truth
> layers:** CEMS coarse blocks (`builtUpA`, areal — do first) and CEMS points (`builtUpP`,
> per-building). Full rationale + per-RQ method in the RQ0 DESIGN doc.

### 4.3 Performance metrics
- **Scored sources (have an analysed AOI): IMPACT v1 + v2, OSU, Microsoft.** Precision / recall /
  F1 via the §4.2 dual-anchor method within the shared analysed extent, at r∈{5,10,20}, per grade.
- **De-prioritized: HOT fAIr, DISHA** — no analysed AOI, so the comparison area can't be bounded
  fairly (DISHA also licence-restricted). Excluded from the headline scoring; may appear as
  qualitative detection-overlap only.
- **UNEP debris (detected-only, no AOI):** scored *only* within fully-enclosed hard-hit admin units
  (§RQ4) under an explicit full-coverage assumption; mass thresholded to a damaged boolean.
- **"Possibly damaged" (CEMS class 1):** [DECISION] recommend headline binary = {Damaged,
  Destroyed} positive, and report a second row including class 1 — it swings every recall number.
- **Aggregate agreement (all products):** correlation / bias of damaged-count and damaged-fraction
  per h3 and per admin unit vs CEMS — the "is the operational picture right" view, which tolerates
  building-level positional error. (This is the *continuous* agreement; the *ranking/triage* view
  is its own subsection, §4.4.)
- **Calibration (where probabilities exist — OSU, DISHA):** reliability of the probability against
  CEMS.

> **[DECISION] which CEMS snapshot.** CEMS grading is delivered incrementally — its *spatial
> coverage grows over time* (10 products delivered / 9 pending as of 06-28; latest-only vs
> cumulative), not a quality issue but a temporal one. Fix the CEMS snapshot/version we score against and state
> it (recommend the final consolidated EMSR884 delivery, `is_latest`).

### 4.4 Prioritization skill & error structure (the paper's core analysis)
Answers: *even when a product is a bad classifier, does it still tell responders where to go — and
if not, why not?* Two coupled analyses at both **h3** and **admin (adm1/2/3)** resolution.

**(a) Prioritization skill — is the ranking right?**
- **Rank agreement** of per-unit damage (count and fraction) vs CEMS: Spearman ρ and Kendall τ.
- **Top-k concordance / precision@k** on the *worst-hit* units — the operationally decisive set,
  since response goes to the top of the list, not the whole distribution. Report overlap of each
  product's top-k units with CEMS's top-k across k (e.g. top-5/10/20 admin units; top-N% of hexes).
- **Rank-vs-magnitude framing:** a product can be badly *calibrated* (wrong absolute counts) yet
  perfectly *ordered*. We report ranking skill independently of count bias to make exactly this
  point.

**(b) Error structure — is the false-positive rate noise or bias?** *This is the crux.*
- Compute the per-unit **over-detection ratio** (product damaged / CEMS damaged) across all units
  within the shared analysed extent.
- **Test for spatial structure in the errors:** is over-detection uniform (random noise → ranking
  robust) or does it correlate with covariates that are *not* damage — e.g. building density,
  land cover / built-up type, distance to coast, terrain/slope, ShakeMap intensity, or a specific
  sub-region? Spatial autocorrelation (Moran's I) on the residuals + regression of the
  over-detection ratio on those covariates.
- **The decision rule this yields:** *unbiased* inflation → the product is a valid prioritization
  layer despite high FP; *biased* inflation → it systematically misdirects and must be corrected
  or discarded for triage. State the threshold/criterion explicitly.
- **SAR-disagreement interpretation (the one caveat to CEMS-as-truth).** For SAR products
  (IMPACT, OSU), a slice of "over-detection" vs CEMS may not be error but *real damage nadir
  optical cannot see* (soft-story collapse with roof intact, internal/foundation damage). The
  same spatial-structure test discriminates: over-detection that is **random** reads as noise;
  over-detection that **clusters with earthquake-intensity covariates** (proximity to epicentre,
  high MMI, on-fault) is a candidate for genuine-but-optically-invisible damage, not FP. This is
  the *only* place a product may be "wrong vs CEMS" yet right — flag it, don't silently penalise
  it, and don't overclaim it (CEMS remains truth for everything it can see).

**(c) The Microsoft false-positive investigation (named case).** Reproduce the externally-reported
high-FP claim: locate where Microsoft over-detects relative to CEMS, test whether it is confined to
the reported sub-region, and quantify whether Microsoft's area-ranking survives with that region
included vs excluded. Generalize the same procedure to every product (we expect elevated FP in
several).

> **[DECISION] prioritization resolution & k.** Which admin level is the operational decision unit
> here — adm2 or adm3? And do we define "worst-hit" by absolute damaged count or damaged fraction
> (fraction favours small hard-hit units; count favours large ones)? Recommend reporting both,
> leading with adm2 + count for the headline. Need your steer.
> **[DECISION] covariate set** for the bias regression — which non-damage covariates do we commit
> to (building density, land cover, coast distance, MMI…)? Drives what ancillary layers we pull.

### 4.5 Availability / utility scoring
- A small qualitative rubric per product: licence/redistribution rights, access channel (HDX vs
  email vs portal), format readiness (analysis-ready vs raw), update cadence, and any AOI/coverage
  limits. This is where DISHA's restriction and UNEP's mass-only output become *findings*, not
  footnotes.

---

## 5. Reproducibility

- All scoring runs off immutable bronze/silver/gold snapshots (ADR-0005) and the common gold facts.
- Ship the analysis as an `exploratory/`-style entry (runnable `analysis.py` + `findings.md`) that
  regenerates every number and figure, plus this paper's tables.
- **[DECISION]** where does the *analysis code* live — under `exploratory/paper/` (git-ignored with
  the manuscript, private) or as a normal numbered `exploratory/NNNN-*` entry (committed,
  reproducible, but visible)? Trade-off: privacy now vs reproducibility/citation later.

---

## 6. Results (planned)

- **6.1 Availability & the release timeline.** The timeline figure; who was first; the licence/
  access findings (DISHA restricted; UNEP mass-only; everything else open via HDX).
- **6.2 Latency.** Event→availability per product; the v1-vs-v2 IMPACT story (fast proxy vs
  corrected vector).
- **6.3 Performance vs CEMS.** Table 2: precision/recall/F1 (AOI products) + overlap (detected-only)
  at building level; h3 cross-check; per-class where graded.
- **6.4 Coverage / completeness.** How much of CEMS's damaged set each product's AOI even had a
  chance to see.
- **6.5 The latency–accuracy frontier.** Scatter of latency (x) vs F1/recall (y), sized by
  coverage — the paper's money figure. Which product dominates the operational Pareto front at
  each point in the response timeline.
- **6.6 Prioritization skill & error structure.** Rank-agreement table (Spearman/τ, top-k
  concordance) per product at h3 + admin — the "does it triage right" result. The over-detection
  bias analysis: for each product, is FP noise or spatial bias (Moran's I + covariate regression)?
  The Microsoft named case: localize its FP, test whether its ranking survives with/without the
  flagged region. **The headline claim lives here** — which noisy products are still valid
  prioritization layers, and which are biased and misdirect.

---

## 7. Discussion

- **Accuracy is the wrong question for triage.** The core discussion point: a product's building-
  level FP rate can be high while its area-prioritization is excellent — *if* the error is
  unbiased. Fast large-area products that rank correctly are valid "where-to-look-first" layers
  that front-run CEMS by days; reframing evaluation from classification accuracy to prioritization
  skill + error structure is the argument the field needs. Conversely, a product with *biased*
  error (e.g. Microsoft's flagged region, if it generalizes) can look accurate on average yet
  systematically misdirect — the more dangerous failure.
- **Which product, when?** Map products onto the response timeline: what's the best available
  signal at 24h / 72h / 1wk, and what do you trade for speed.
- **SAR vs optical** under this event's conditions (cloud, terrain, coastal).
- **The cost of "detected-only."** Products without an analysed AOI can't be scored and are
  operationally ambiguous (absence ≠ safety) — an argument for providers to always ship coverage.
- **Licence as a first-class operational constraint** (DISHA): a technically strong product with
  restricted rights may be less useful than a weaker open one.
- **Ground-truth scope, not accuracy:** CEMS is ground truth for *visible-from-above* damage
  *within its analysed extent*. So a SAR product's disagreement with CEMS is usually error, but a
  spatially-structured slice of it (near the epicentre / high-MMI) may be real damage of a class
  nadir optical cannot see (soft-story collapse, internal/foundation damage). We use the §4.4b
  error-structure test to flag that slice rather than reflexively scoring it as false positive —
  the one place a product can be "wrong vs CEMS" yet right.

## 8. Limitations

- Single event, single hazard (earthquake), single geography — external validity. **(This is the
  principal limitation and the real cap on generalizability — not the ground truth, which is sound.)**
- Ground truth is bounded by CEMS's analysed extent (coverage) and by nadir-optical visibility
  (a narrow invisible-from-above damage class) — scope bounds, handled explicitly, not accuracy gaps.
- Our-ingest vs true-release latency uncertainty pending provider confirmation.
- Footprint/base heterogeneity and snap error (link exploratory/0001, /0003).
- Class-scheme collapse loses grade information.

## 9. Conclusions & recommendations

- For responders: a decision guide (speed/accuracy/rights) keyed to the response phase.
- For providers: ship analysed extents; clarify licences up front; standardise on a common base.
- For the community: adopt a shared evaluation framework (this one) per activation.

---

## Appendices (planned)
- A. Per-product provenance & exact snapshot versions scored.
- B. Full confusion matrices per product/class/unit.
- C. Timeline reconstruction detail (ledger + git + provider confirmations).
- D. Harmonization / snap-matching sensitivity (building vs h3 vs admin).

---

## Open decisions collected (for our next pass)
1. ~~"Ground truth" → "reference standard"?~~ **RESOLVED: CEMS is ground truth** (expert VHR
   interpretation; scope-bounded by coverage + visibility, not accuracy). (§Title, §4.4b)
2. Single-event case study vs reusable framework framing? (§1)
3. Include UNEP debris quantitatively, or qualitative only? (§3)
4. Report IMPACT v1 *and* v2 separately? (recommend yes) (§3)
5. Latency zero-point = USGS event origin time? (§4.1)
6. How aggressively to chase provider release dates now? (§4.1)
7. Headline matching unit = building-level, h3 as cross-check? (§4.2)
8. Which CEMS snapshot/version is the frozen reference? (§4.3)
9. Analysis code: private under `exploratory/paper/` vs committed `exploratory/NNNN-*`? (§5)
10. Prioritization decision unit (adm2 vs adm3) and "worst-hit" by count vs fraction? (§4.4)
11. Covariate set for the over-detection bias regression (density / land cover / coast / MMI)? (§4.4)
