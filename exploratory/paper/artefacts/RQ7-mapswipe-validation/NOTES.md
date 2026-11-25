# RQ7 — MapSwipe/HOT crowd validation — running notes

Value-demo BEFORE ingestion (user gate, 2026-07-14). Script `scripts/rq7_west_cluster.py` ·
`rq7_west_cluster_join.csv` · `figs/rq7_west_cluster_adjudication.png`. Data = raw MapSwipe
exports re-downloaded to scratchpad (NOT in the lake yet); 0=No damage / 1=Damaged / 2=Not sure
(labels confirmed from project configs via GraphQL).

## Question
Does the 400+-volunteer crowd adjudicate the RQ3b Microsoft west-Caraballeda over-detection
cluster — genuine MS FP vs CEMS under-enumeration?

## Result — adjudication works at STRIP scale, not at cell scale
1. **Strip scale (strong):** Catia La Mar / west (project 3179, 3,462 MS-seeded hexes,
   22k votes): **71% majority-"No damage", only 13% majority-"Damaged"**. Caraballeda / east
   (3178, 433 hexes): 49% No / 48% Yes. The crowd declines to confirm the large majority of
   MS flags across the west strip while confirming half in the damage-dense east — the same
   macro gradient as the RQ3b residual field. Combined with LOW crowd confirmation inside the
   cluster (task-weighted 0.23 vs 0.27 elsewhere), this argues **against** the
   "CEMS-incompleteness" attribution (the crowd does not see abundant damage CEMS missed) and
   **for** genuine MS over-detection — the first independent human evidence on the §4.5
   investigation.
2. **Cell scale (null, honest):** joined at H3 res-8 (88 cells, 3,771 tasks), crowd rejection
   does NOT track the residual gradient (Spearman rho=+0.08, p=0.43; cluster-vs-rest
   confirmation 0.23 vs 0.24 ns, unsure 0.26 vs 0.26 p=0.056). Candidate reasons:
   (a) **vintage mismatch** — MapSwipe tasks were seeded from later MS runs (Vantor/SkySat/
   BlackSky HDX products), not our silver MS set; (b) shallow west vote depth (4–7) + ~25%
   "Not sure"; (c) res-8 parent join blurs ~50 m tasks; (d) the residual conditions on
   CEMS+exposure, the crowd saw raw hexes. The right cell/point-scale test is the
   **label-transfer bridge**: match crowd hexes to the exact seeded detections (vintage-matched)
   — needs ingestion + MS-product vintage reconciliation.

## Assets beyond this demo (from the profiling pass)
- 14 projects; El Junquito 3210/3211 (fAIr-only, 2,844 cells) = reference data in a CEMS-free
  area; 3195 Moron overlaps CEMS Moron; 3173 = only per-point set (86 AI pts + prob vectors);
  3188 = res-12 (~22 m, quasi-point). HDX synthesis ("verdict": accepted 638 / uncertain 4,246)
  drops the "No damage" class — use RAW exports for FP adjudication.

## Verdict on ingestion
Worth bronzing: strip-scale adjudication of the MS cluster is real evidence; plus crowd-vs-CEMS
calibration (3178/3195), CEMS-free reference (El Junquito), per-source precision (fair vs
microsoft columns). Ingest RAW MapSwipe exports (primary) + HDX synthesis (citable provenance).
Scratchpad copies are ephemeral (already wiped once) — do not analyse further without bronzing.

---

# RQ7b — crowd adjudication of consensus FPs (2026-07-15)

Script `scripts/rq7_consensus_fp_adjudication.py` · `rq7_consensus_fp_adjudication.csv`.
Terminology fixed: "k-of-4 vote" = rule (>=k of MS/IMPACT/OSU/UH flag the building), never a
metric. Quad region; CEMS match r=10; crowd = bronze MapSwipe hexes, >=4 votes, majority.

| rule | flagged | CEMS-TP | CEMS-FP | FP crowd-damaged | TP crowd-damaged | P floor | P adj |
|---|---|---|---|---|---|---|---|
| 3-of-4 | 2,990 | 602 | 2,388 | 0.26 | 0.58 | 0.201 | **0.409** |
| 4-of-4 | 459 | 237 | 222 | **0.62** | 0.68 | 0.516 | **0.816** |

- 4-of-4 CEMS-"FPs" are crowd-confirmed damaged at nearly the TP rate (0.62 vs 0.68) —
  full-consensus flags that miss CEMS are almost as good as ones that hit it. Adjusted
  precision conservative (crowd confirms only 68% of even CEMS-verified damage; ratio-
  calibrated estimate would be higher still).
- Directly arbitrates the "which buildings, with all those FPs?" objection: the 4-of-4
  check-first list is right ~4-in-5; 3-of-4 is a genuine mixture (~0.4 adjusted).
- Unifies RQ2e (CEMS misses lighter damage) + RQ5 finding 5 (consensus-as-CEMS-gaps):
  same phenomenon, now quantified from two independent references.
- Caveats: crowd hexes ≈50 m (verdict transfers to building only approximately); MapSwipe
  seeded from MS+fAIr detections → crowd coverage of consensus flags is not random (84–97%
  covered here, so mild); crowd vintage/newer MS runs caveat as RQ7.

## Volunteer imagery provenance (2026-07-22)

How to get it: GraphQL `publicProjects → projectTypeSpecifics → ... on
ValidateProjectPropertyType → tileServerProperty { name custom { url credits } }`
(GET; introspect `ProjectRasterTileServerConfig`/`...CustomConfig` for field names).
All 24 projects use CUSTOM tile servers: either direct `tiles.openaerialmap.org/<oam_id>/...`
or HOT titiler wrapping `oin-hotosm-temp.s3...<oam_id>/0/<file>.tif` (unwrap the `?url=`
param). Credits: "OpenAerialMap" (round 1), "Vantor WorldView-3 (0.32 m) via OAM" (round 2).

Dates: most items are NOT in the public OAM API (temp bucket). Three sources of truth:
COG `TIFFTAG_DATETIME` (only La Mar (1): **2026-06-27 11:26 UTC**, sun_elev 16.8°);
public OAM metadata (El Junquito (1): acquired 2026-06-25); MongoDB ObjectId upload
timestamps (all items: uploaded 2026-06-26 → 06-30, bounding acquisition ≤ those dates).

Also verified: `tasks_<id>` files enumerate the full seeded hex universe and match the
agg export 1:1 on finished projects (3179: 3,482 = 3,482, min 4 votes; 3211: 2,214 =
2,214, min 9) — assessed-vs-never-shown is explicit; there are no zero-vote rows.

## Round 2 — Catia La Mar re-vote, project 3248 (2026-08-07, POST-FREEZE)

Completed 2026-08-05 (progress 1.0; 54,305 results vs 52,230 required; 728 contributors;
votes 2026-07-15 → 2026-08-05). Re-serves the IDENTICAL 3,482 res-11 cells as 3179
(h3 sets verified equal) at median 16 votes/task vs round 1's 6.

**The instrument changed.** Options are 1 = "Yes" and 2 = "Not Sure", whose description
explicitly absorbs "there is no damage"; the round-1 answer 0 = "No" does not exist (raw
export contains only 1s and 2s across all 54,304 votes — same collapse as HOT's HDX
synthesis). The frozen 71%-majority-No statistic is therefore not re-testable by design;
only confirmation-side statistics transfer across rounds.

**Imagery:** different OAM item from round 1 (r2: `6a43873f…`, uploaded 2026-06-30,
credits "Vantor WorldView-3 via OAM"; r1's scene is TIFF-dated 2026-06-27). Same vendor
pipeline and post-event vintage window, but not pixel-identical — cross-round verdict
differences are partly attributable to imagery, not only to crowd or instrument.

**Ingest & freeze protection:** landed additively via the new
`pipelines/ingest_mapswipe.py --project 3248` mode (manifest merged, HDX skipped; blob
etag diff verified nothing else changed). All pooled frozen loaders
(rq2g/rq2i/rq5b/rq7_consensus/rq8) now skip post-freeze partitions via
`gie_paper.MAPSWIPE_POSTFREEZE`; the pooled frozen-verdict series is md5-identical
before/after ingest (`d6e0689c…`). Round-2 analysis opts in explicitly.

**Scripts/outputs:** `rq7_round2_replication.py` → `rq7_round2_replication.csv`,
`rq7_round2_crosstab.csv`, `rq7_round2_padj_sensitivity.csv`;
`rq7_round2_explainer_fig.py` → `figs/rq7_crowd_adjustment_explainer.png` (the
two-panel mechanism map, also embedded in the deck and manuscript appendices).

Headlines (details in the register, RQ7c): confirmation replicates in aggregate
(majority-Yes cells 12.9% → 11.1%; flag level, the rq2i quantity, 13.2% → 11.5% of MS's
7,661 unmatched strip flags); per-hexagon verdicts are unstable but mostly from voting
noise (share-variance is 68%/36% noise; reliability 0.32/0.64; latent cross-round
correlation +0.63 vs raw +0.29); swapping r2 verdicts into the strip moves as-delivered
P_crowd_adj by −0.031…+0.015 with no ordering changes.
