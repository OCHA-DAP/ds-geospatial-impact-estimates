# RQ2 — sources vs CEMS damage POINTS (builtUpP) — PRIMARY performance analysis

Script `scripts/rq2_points.py` · `rq2_points_summary.csv` · `figs/rq2_pr_f1_r10.png`.
Dual-anchor native matching (RQ0). CEMS points native; products native footprints; distances in
EPSG:32619. r∈{5,10,20}. Headline positive = {Damaged, Destroyed}; also reported incl. Possibly.

## Headline (dmg+destroyed, r = 10 m)
| product | recall | precision | F1 | CEMS pts (denom) | product bldgs (denom) |
|---|---|---|---|---|---|
| **OSU** | **0.856** | 0.056 | 0.105 | 1,476 | 31,271 |
| Microsoft | 0.614 | 0.123 | 0.205 | 1,456 | 7,868 |
| IMPACT v2 | 0.611 | 0.049 | 0.091 | 1,509 | 22,951 |

Radius sensitivity (recall→ / precision→ grow with r): OSU recall 0.81→0.86→0.91 (r=5/10/20);
MS 0.55→0.61→0.70; IMPACT 0.56→0.61→0.68. Full grid in the CSV.

## What's trustworthy vs what's entangled
- **RECALL is the solid metric.** How much of CEMS's *confirmed* damage each product catches:
  **OSU 0.86** (S1 coherence finds most CEMS damage), **MS & IMPACT ~0.61**. Clean, interpretable,
  robust to the caveat below.
- **PRECISION is low (0.05–0.12) AND structurally entangled — do NOT read it as "88–95% wrong."**
  Products flag **5–20× more** damaged buildings than CEMS has points in the same region (MS 7.9k /
  IMPACT 23k / OSU 31k flagged vs ~1.5k CEMS damage+destroyed points). Precision is therefore
  **capped by CEMS point density**: most product buildings simply cannot be within r of one of the
  ~1,500 CEMS points, regardless of correctness. Two non-exclusive explanations:
  1. **Genuine over-detection** (the high-FP concern) — products call far more damage than CEMS.
  2. **CEMS point incompleteness** — builtUpP may not point-map *every* damaged building in the
     analysed extent, so some product "FP" are real damage CEMS didn't enumerate.
  RQ2 cannot separate these. **That separation IS the thesis → RQ3** (is the over-detection spatially
  *structured* = bias, or *diffuse* = noise-but-still-rank-preserving?).

## Reading against the paper thesis
This is exactly the setup: **high recall (esp. OSU), low precision.** The paper's question is not
"is precision low" (it is) but "does the over-detection still rank areas correctly for triage"
(RQ3). RQ2 quantifies the cost; RQ3 tests whether it's payable.

## Caveats / next
- Precision's structural cap: consider reporting **recall as headline**, precision as
  "over-detection ratio" (product bldgs per CEMS point) rather than a naive precision — it's the
  honest framing and feeds RQ3's over-detection analysis directly.
- Per-AOI split (Caraballeda dominates CEMS points 2,770/3,072) — global numbers are Caraballeda-
  weighted. Break out by AOI.
- Add IMPACT v1 (local re-materialisation) for the v1↔v2 contrast.
- Grade-stratified recall (Destroyed vs Damaged vs Possibly) — do products catch severe damage better?

---

# RQ2c — density-mirror null, per CEMS analysed area (2026-07-07)

Script `scripts/rq2_density_null.py` · `rq2_density_null.csv`. Trigger: user skepticism that AI
products "just mirror building density" (and the observation that RQ3b's Moran/offset test did NOT
test that — it tested residual structure *after* conditioning on CEMS). Direct discriminators, per
CEMS analysed area: **enrichment** = recall ÷ flag-fraction (density mirror ⇒ ~1) and the
**flag-rate contrast** between hard-hit and ~undamaged CEMS areas (density mirror ⇒ flat rate;
robust even where CEMS has only 3 points, since CEMS analysed the whole area and found ~nothing).

## Flag rate (% of buildings flagged) by CEMS area
| product | Caraballeda (1,455 pts) | Caracas (3 pts) | Santa Cruz (3 pts) | Moron (26 pts) | San Felipe (14 pts) |
|---|---|---|---|---|---|
| OSU | **45.4** | 2.5 | 0.9 | 13.5* | 1.1 |
| IMPACT v2 | **19.0** | 8.5 | 1.2 | 6.7 | 1.8 |
| UH | 9.5 | **17.7** | **27.5** | 1.9 | — |
| MS | 16.1 | — (no AOI) | — | — | — |
\* OSU Moron overlap is only 4,074 buildings (edge sliver).

## Findings
1. **OSU & IMPACT emphatically pass the density-mirror test — at AREA scale.** OSU's flag rate
   contrasts ~50:1 between Caraballeda and the undamaged areas (45.4% vs 0.9–2.5%); IMPACT ~8:1.
   A density mirror is flat. Their skill is *concentration in the right places*.
2. **…but within Caraballeda, per-building discrimination is weak** (enrichment: OSU 1.5,
   IMPACT 2.4, MS 3.0, UH 3.6; precision lift over a random flagger 1.9–3.9). The products are
   far better at *where* than at *which building* — the cleanest micro-scale statement yet of the
   paper's RQ3 thesis.
3. **UH FAILS the area contrast — the "garbage" instinct is validated for UH outside the coast.**
   It flags MORE where CEMS found nothing (Caracas 17.7%, Santa Cruz 27.5%) than in Caraballeda
   (9.5%). Whatever drives its inland flags, it is not earthquake damage (candidates: model
   transfer failure, different imagery vintage, urban-fabric response). Yet inside Caraballeda UH
   has the BEST per-building precision (0.093, lift 3.9) — signal on the coast, hallucination
   inland. Explains both the RQ5 result (UH useful in the quad/Caraballeda ensemble) and its
   atrocious full-region single score (P=0.009).
4. RQ5's global enrichment table (OSU 8.8×) conflates the two scales; per-area is the honest cut.

## Caveats
- Caracas/Santa Cruz recall/precision cells are meaningless (3 points) — only flag rate is robust
  there. It assumes CEMS's near-zero found-damage in those extents is trustworthy (ground-truth
  claim + visibility bound; check CEMS Caracas monitoring coverage/dates before hanging UH publicly).
- Same construction-basis caveat as RQ5 (Overture centroids, gold flags).

---

# RQ2d — Microsoft's confidence axis (2026-07-14)

Script `scripts/rq2_ms_confidence.py` · `rq2_ms_confidence_curve.csv` ·
`figs/rq2_ms_confidence_curve.png`. MS silver fields we binarise everywhere: damage_pct_10m
(continuous), num_observations (1-3 scenes), uncertainty (sparse). Native footprints,
CEMS∩MS region (2,922 CEMS pts), dual-anchor r=10.

1. **The confidence curve is FLAT** — sweeping damage_pct_10m buys precision 0.10→0.19 max
   while recall collapses 0.66→0.10. Shipped binary flag (P=0.121, R=0.613, F1=0.203) sits
   slightly ABOVE the raw-pct curve at its recall (their classifier adds a little) and near
   the curve's best F1 (0.228 @ pct≥0.5) — the operating point was reasonably chosen; there
   is no hidden headroom. Third instance of the modality-floor law (IMPACT∧OSU plateau,
   RQ6 DIY curve): single-product confidence tuning cannot approach the cross-modal
   ensemble (3-of-4 sits above the entire curve).
2. **num_observations IS a strong quality signal**: shipped-damaged with 2+ scenes
   P=0.245 vs 1 scene P=0.097 (2.5×; 1,332 vs 6,691 flags). Self-corroboration = an
   intra-product mini-ensemble. Candidate for west-cluster mechanism (is the cluster 1-obs?)
   and for a "high-confidence MS" ensemble member.
3. **ChatMap field points** (NEW on HDX; bronzed under source=mapswipe/hdx): 415
   field-validated damage points ('complete' 328 / 'significant' 63 / 'minimal' 24).
   Shipped MS finds 73% within 10 m / 80% within 20 m of field points in its AOI — a
   recall-side check from a fully independent, ground-based reference. Positives-only
   (opportunistic field reports) → miss-side sample, complement to MapSwipe's FP-side.

Note: bronze/source=mapswipe now exists (pipelines/ingest_mapswipe.py, re-runnable refresh;
24 projects — campaign still growing: new Carayaca/Catia La Mar/Caracas 2/La Guaira 2
projects, some pre-export).

---

# RQ2e — systematic recall vs ChatMap field points (2026-07-14)

Script `scripts/rq2_chatmap_recall.py` · `rq2_chatmap_recall.csv` ·
`figs/rq2_chatmap_found_by.png`. 415 field points; per product restricted to ITS AOI;
r=20 m primary (phone GPS + reporter-offset), 10/50 sensitivity; flags = gold building_flags.

## Recall @ r=20, within own AOI
| ref | n | overall | complete | significant | minimal |
|---|---|---|---|---|---|
| OSU | 415 | **0.85** | 0.92 | 0.71 | 0.21 |
| **CEMS {2,3}** | 381 | **0.85** | **0.94** | **0.49** | 0.17 |
| MS | 376 | 0.74 | 0.82 | 0.33 | — |
| IMPACT v2 | 415 | 0.66 | 0.73 | 0.46 | 0.25 |
| UH | 388 | 0.54 | 0.59 | 0.23 | 0.45 |
| ≥1-of-4 (union) | 376 | **0.95** | 0.97 | 0.85 | — |
| ≥3-of-4 | 376 | 0.67 | 0.74 | 0.31 | — |
Detected-only hit-rates (no AOI, not comparable): UNEP debris 55%, DISHA 17%, fAIr 2%.

## Findings
1. **CEMS itself misses field-reported damage — grade-dependently.** Within its own extent,
   CEMS has a {2,3} point within 20 m of 94% of 'complete' field points but only **49% of
   'significant'** and 17% of 'minimal'. First *quantified, field-based* evidence for the
   CEMS-under-enumeration side of the RQ2/RQ3b attribution caveat: CEMS is near-complete on
   destruction, materially incomplete on lighter damage. (Field grades ≈ severe-skewed, so
   these are the easy cases — the true lighter-damage gap is likely larger.)
2. **Grade gradient is universal**: every product (and CEMS) catches 'complete' far better
   than 'significant'/'minimal'. Satellite damage detection ≈ destruction detection.
3. **OSU ties CEMS on field recall (0.85)** — remarkable for an automated product; matches
   its RQ2 max-recall profile. UH weakest (0.54) in-AOI.
4. **The union finds 95%** of field-confirmed damage — but ≥3-of-4 drops to 0.67:
   consensus buys precision (RQ5) at a real field-recall cost; the P-R trade is now
   grounded in ground truth, not just CEMS.
5. **The inland gap** (fig): ~40 eligible field points (11%) have NO product flag within
   20 m, concentrated inland (El Junquito / Caracas hills) — where products' coverage and
   attention were thinnest. Every field point falls inside ≥1 product AOI (0 fully outside),
   so these are genuine misses, not coverage holes.

## Caveats
- Positives-only reference (opportunistic reports): recall only, never precision; severity
  mix skewed to 'complete' (79%).
- No date/collector metadata in the file — vintage unknown (ask HOT); some reports may
  postdate product acquisitions.
- Centroid-basis flags; r=20 absorbs most of it (r=10/50 in CSV bracket the story).

## RQ2d addendum — MS west/east zone split (2026-07-17, MS-call prep)
Native footprints, CEMS latest, r=10, region = CEMS ∩ MS AOI, split at lon −67.03:
WEST (single-scene zone): 15,356 bldgs, 4,412 flagged (28.7%!), 217 CEMS pts → P=0.052
R=0.811 F1=0.098 (recall inflated by blanket-flagging — same 28%-flag signature as UH Santa
Cruz). EAST: 47,310 bldgs, 3,611 flagged (7.6%), 1,250 CEMS pts → P=0.205 R=0.578 F1=0.303
(best single-product zone measured). East precision 4× west; confirms the single-scene
failure quantitatively. On the MS call deck (map slide annotations).

## RQ2g — Vantor Jun-25 vs Planet Jun-26, same buildings (2026-07-17)
Script `scripts/rq2g_scene_headtohead.py` · `rq2g_scene_headtohead.csv`. Per-scene HDX gpkgs;
Planet's 24,732 footprints ⊂ Vantor's 30,761 (shared ids). Overlap: V flags 27.8%, P 4.9%;
conflicts V-dmg/P-intact 6,502, P-dmg/V-intact 841, both 368. CEMS on stock: 115 pts (thin).
FINDINGS: (1) Planet = restraint not accuracy — its flags crowd-confirmed at 7% vs Vantor's
14%; recall 0.07 vs 0.37. (2) MS tie-break directionally right (68% of overruled = crowd-no)
but discarded ~845 crowd-visible damages. (3) Even both-scene agreement is 72% crowd-rejected
in this low-damage zone → per-scene calibration (HASTE fresh-model-per-scene), not sensor,
is the dominant factor; provider comparison remains confounded (day, model, area).
Caveats: CEMS n=115; crowd coverage asymmetric (100% V / 59% P — tasks seeded from merged).
