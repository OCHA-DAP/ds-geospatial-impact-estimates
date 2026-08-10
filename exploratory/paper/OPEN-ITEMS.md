# Open items — VE damage-product evaluation paper

## 0. TOP PRIORITY — two-region reframe (user directive, 2026-08-07)

**STATUS 2026-08-07 late: steps 1–3 DONE.** Core ranking artefact run
(rq3f_null_ranking_core.csv: single null 0.648 res 8; 3–3 split), figure rebuilt
(panel B = bars vs one red line), v3 rewritten to the two lenses, and the scorecard
core numbers re-sourced and verified from rq5b_six_member.csv (P 0.045–0.093,
R 0.31–0.69; abstract updated 0.04–0.09 -> 0.05–0.09). Terminology: "best case" ==
core, introduced as best case once (user rule); no lint wanted. REMAINING: step 4
(user decides fig-peraoi's fate + the appendix's retired AOI-run table), step 5
(deck inherits).

**Rule: the paper compares in exactly two regions, ever — the core region (61 km²
Caraballeda-coast intersection, one shared cell set) and as-delivered. The Caraballeda
AOI is retired as a comparison frame** (the user never intended it as one; it caused
repeated confusion including for the author). Work, in order:

1. Run the missing artefact: RQ3f ranking under the CORE lens, i.e. simply the
   existing 61 km² core region (the same one voting/fusion use; by construction all
   products share its cells, so the geography model gets one value). NOT a new or
   combined region. Frozen inputs; write CSVs like the existing rq3f pair. Until it
   exists, v3's ranking section has only the as-delivered test.
2. Re-source the scorecard "best case" from core-region artefacts: per-product core
   precisions exist (fusion-frame CSVs: 0.040–0.093; tbl-frames row set); recalls need
   pulling from rq8/rq2 core artefacts and verifying pairwise before any swap of the
   quoted 0.04–0.09 / 0.31–0.69 numbers in abstract + sec-flags.
3. Rewrite v3 (abstract, sec-flags, sec-ranking, @tbl-regions back to TWO regions,
   region tags) and re-verify every number against artefact CSVs.
4. Decide the per-AOI figure's fate: keep as the reference-concentration/dead-zone
   DIAGNOSTIC (relabelled so it cannot read as a reporting region) or drop to appendix.
   User to confirm.
5. Deck inherits the reframe at next deck touch (it quotes AOI-based best-case numbers).
6. Supersedes OPEN-ITEMS 3c (the optional common-cells run is now mandatory step 1).

Parked analysis gaps and improvements, so they survive session changes. Ordered by how
much they protect the paper's claims, not by effort. Dated 2026-08-07; strike items here
(with a date) rather than deleting them.

## Analysis gaps

**1. Buffered spatial cross-validation (top defensibility item) — EXECUTABLE SPEC.**
WHY: the null and fusion are validated by GroupKFold over H3 res-7 blocks (`cell7`) in
`rq8_learned_fusion.py` with no buffer; adjacent blocks share edges, damage risk is
smooth, so the leak flatters the smooth models (null, fusion) against the products in
the same direction every fold. Stakes RAISED 2026-08-09: the radius table shows the
null gaining fastest with radius (F1 .128/.206/.282) — a pattern a reviewer could blame
on the same leak. HOW: add `GIE_CV_BUFFER_M` (default 0) to rq8_learned_fusion.py; per
fold, build a KDTree on TEST-fold building coords and drop TRAINING buildings within
the buffer (run 300 and 500 m variants); outputs suffixed `_bufN`. Also fit density9 on
train-only as a variant OR add the one Methods clause (covariate-only transduction,
pre-event data). NUMBERS TO WATCH: core null logistic F1 0.128 / AP 0.060; fusion F1
0.343 / AP 0.284 (products don't move — they are not CV'd). DECISION RULE: drop < ~0.01
F1 → add a "checked with buffered CV" sentence to Limitations + register entry; bigger
drop → soften, in order: abstract ("None separated itself…"), sec-null takeaway,
tbl-nulltally caption, appendix radius reading, Summary. SECONDARY: rq3f's null (same
GroupKFold machinery, own fit) and rq8b's per-footprint nulls inherit the question —
re-run core ranking with buffer if the primary result moves. Register entry required
either way.

**2. Bootstrap confidence intervals — EXECUTABLE SPEC.**
WHY: every headline number is a point estimate; claims now leaning on CIs: "null 0.128
inside the product range (0.085–0.148)", the 3–3 ranking splits, OSU v0/v1 "minimal"
(P .036 vs .034, R .68 vs .64), dial-rule orderings. HOW: block bootstrap — resample cells WITH
replacement (never buildings; neighbours are correlated), ~2,000 reps. BLOCK SIZE
MATTERS: the core region holds only ~13 res-7 cells (too few to bootstrap), so use
res-8 blocks for core-region intervals (133 blocks) and res-7 for as-delivered.
Resample the SAME cells jointly for all predictors so paired DIFFERENCE intervals are
valid (e.g. UH − null), which is the decision-relevant interval; recompute P/R/F1 for each product (shipped lists), each
k-of-6 rule, and the null/fusion (using frozen out-of-fold scores — do NOT refit per
rep), percentile 95% intervals. Build on whatever CV design survives item 1. OUTPUT: a
CSV per frame + intervals into tbl-dial (± or sub-script) + delete the Limitations
"pending" sentence + register entry. ALSO promised in the same Limitations sentence and
unstarted: population-weighted prioritisation.

**3. ~~Coherence-claim symmetry~~ — CLOSED 2026-08-07.**
The coherence-side numbers already existed in the frozen artefacts (rq2_density_null.csv:
IMPACT 1.2%, OSU 0.9% flag rate in the Santa Cruz control, vs amplitude rebuild 8.0% and
optical UH 27.5%). The full four-way comparison is now printed in "The event and the
products", stated as flag rates only (no mechanism attributed to UH's failure).

**3b. Candidate fourth reference: terremotovenezuela.com citizen reports (2026-08-07).**
Microsoft's public report validates against 221 citizen damage reports (of 925 total)
from terremotovenezuela.com, severity-graded, with location error they characterise as
median 2.1 m plus a long tail. We have never used this source. Check: overlap with
ChatMap's 415 points, ingestibility, and whether it adds inland coverage. Their report
also leaves validation provenance unstated (no in/out-of-sample statement, no sampling
method, no annotator-independence note) — relevant if anyone cites their per-scene
precision/recall against ours.

**3c. ~~Common-cells core-region ranking run~~ — DONE 2026-08-07 (see item 0):
rq3f_null_ranking_core.csv, single null value, in the paper as ranking test 2.**

**4. Timeliness × accuracy.**
Blocked on confirmed provider release dates for UH and LIST (register flag #7; our
ingest dates are upper bounds only). The provider e-mail should also ask for LIST's
methodology document (its radar/ResNet basis is provider-stated, not documented —
register flag #14) and UH's acquisition dates/scenes (vendor-level Vantor is
author-confirmed; per-scene attribution is not, which bounds how hard the RQ2o
"same vendor" comparison can be pushed).

## Regression checks owed (cheap, run before item 1)

Scripts modified 2026-08-07/09 without the repo's byte-identity re-run: `rq5b_six_member.py`
(R_CEMS -> GIE_LABEL_R env, default 10) and `rq3f_null_ranking.py` (core scope + cell-set
filter guarded by SCOPE). Re-run each at defaults and `git diff` the frozen CSVs
(rq5b_six_member.csv; rq3f_null_ranking.csv; GIE_SCOPE=caraballeda variant). Expect
byte-identical; any diff means the guard leaked into the default path — fix before
trusting the new _r20/_r30/_core artefacts.

## Code-audit session (batch these together)

- Crowd-verdict lookup is copy-pasted **six** times (rq2g, rq2i, rq5b,
  rq7_consensus_fp_adjudication, rq8, rq7_round2_replication) with a res-11/12
  inconsistency in rq8's crowd-gap mask. Extract one helper in `gie_paper` (all six now
  also carry the post-freeze exclusion, added 2026-08-07).
- UH's derived AOI counts NA-as-negative buildings in its dilation ring.
- `rq5b_six_member.csv` lacks a crowd-coverage column, so the frontier figure's whiskers
  carry no thin-coverage caveat (UH's core-region crowd coverage is 0.27).
- RQ3's error-structure GLM covers only MS/IMPACT/OSU (extents); extending to the other
  three is flagged in the manuscript as open work.

## Content pass (user-directed, AFTER the humanizer pass completes)

Decided 2026-08-07 to keep content review separate from the language pass. Status:

- ~~Scrub the DIY radar rebuild from the manuscript~~ — DONE 2026-08-07 (commit
  "content pass A"): Results list item removed and renumbered; sensing appendix keeps
  the coherence 1.2%/0.9% vs optical 27.5% contrast only. Register keeps RQ6.
- ~~Positive-voice AP passages~~ — DONE 2026-08-07 (pass A): both passages state the
  practice; appendix keeps the derivation.
- ~~Structure review implementation~~ — DONE 2026-08-07 (passes B and C, per
  reviews/2026-08-07-structure-quick-review.md): Results II split (new "Results III:
  the scorecard in both frames", #sec-asdelivered; old III/IV renumbered IV/V);
  @tbl-nulltally tally table + three signposts (issue 2 implemented as
  table+signposts, NOT full relocation — the three comparisons answer different
  questions in place); @tbl-regions reporting-regions box in Methods; flattery caveat
  moved into sec-dial; Discussion's two unanchored results promoted (Methods test
  descriptions + Results I numbers); Methods fairness trim; hedge dedup (conservative:
  Results I second repetition only); crowd re-vote collapse in Methods; Results IV
  ends on arithmetic; contribution bullets carry section refs.
- **Causal framing of the Microsoft west-strip failure** (user flag, 2026-08-07): the
  solid claim is "traced to a single scene"; whether the cause was the image itself or
  the model's handling of it is open at scene level (the UH cross-check is vendor-level
  only). Sweep Results V, the recommendations, and the deck for phrasing that asserts
  per-scene *processing/calibration* as established cause; metadata sentence already
  cut from the abstract. STILL OPEN.
- General content review (user, with fresh eyes). STILL OPEN. Note: the deck is now
  structurally out of sync with the manuscript in minor ways (section numbering
  references, the rebuild still appears on no deck slide — verify) — reconcile at next
  deck touch.

## Editorial / publishing

**5. ~~Humanizer pass over `manuscript_v2.qmd`~~ — COMPLETE 2026-08-07 (pending user's
final read).** All ~190 prose em dashes resolved across five iterations (Abstract →
Appendix); survivors are exempt (table empty-cell markers, figure-code strings,
numeric-range and precision–recall en dashes). Ground rules that applied: technical
terms keep their names with a plain gloss; numbers, crossrefs, math, code untouched.
Deck was explicitly out of scope. Remaining: user read-through, then republish.

**6. Deck one-word fix (with next deck republish).**
"Independent failure modes" slide says UH ran on "the same commercial imagery source as
Microsoft's failing scene" — scene-level is unconfirmed; change to "the same imagery
vendor" to match the manuscript's hedge.

**7. product_scorecard.csv — keep and regenerate (decided 2026-08-07).**
It is an orphan (hand-assembled in the ms_call era, quoted nowhere) and stale twice: UH's
area-ranking ρ is now −0.09 in `rq3f_null_ranking.csv` (headline-relevant, scorecard says
"n/a"), and its MS ρ 0.607 is the native-footprint value where the gold-basis number is
0.585. Decision: do NOT delete — write a producer script that regenerates it from the
frozen artefact CSVs so it can serve as the one-table results catalogue.

## Watch items

- MapSwipe round 2 (project 3248): analysed and published 2026-08-07 (register RQ7c) —
  CLOSED. Residual: the round-2 OAM imagery item's acquisition date is upload-bounded
  (≤ 2026-06-30), not tag-confirmed.
- Before any external submission: re-verify freeze freshness (MapSwipe/HDX/ChatMap) as
  done on 2026-07-20.
