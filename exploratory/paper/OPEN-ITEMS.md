# Open items — VE damage-product evaluation paper

Parked analysis gaps and improvements, so they survive session changes. Ordered by how
much they protect the paper's claims, not by effort. Dated 2026-08-07; strike items here
(with a date) rather than deleting them.

## Analysis gaps

**1. Buffered spatial cross-validation (top defensibility item).**
The geography null and the fusion are validated on ~5 km² spatial blocks with **no buffer
between adjacent blocks**. Damage risk varies smoothly, so a building near a test-block
edge has near-clones in the training blocks; that leaks in the same direction every fold
and specifically flatters the smooth models (the null and the fusion) relative to the
products. It is the strongest remaining attack on the "no product clearly beats the
null" headline. Work: re-run `rq8_learned_fusion.py` with a buffer (drop training
buildings within ~300–500 m of any test block); if the null's F1 0.128 barely moves, say
so; if it drops materially, soften the headline. Either way add a Limitations paragraph
**together with the result** (the audit flagged its absence). Related, minor: the
`density9` feature is computed over all buildings including test rows — covariate-only
transduction, defensible because footprints are pre-event data, but worth one Methods
clause.

**2. Bootstrap confidence intervals.**
Promised as "in progress" in Limitations. Every headline number is a point estimate;
close calls (products 0.085–0.148 vs null 0.128) may not survive intervals. Must be a
**block bootstrap** (resample spatial blocks, not buildings — same reasoning as item 1),
and should be built on whatever CV design survives item 1. Population-weighted
prioritisation is promised in the same Limitations sentence and is also unstarted.

**3. ~~Coherence-claim symmetry~~ — CLOSED 2026-08-07.**
The coherence-side numbers already existed in the frozen artefacts (rq2_density_null.csv:
IMPACT 1.2%, OSU 0.9% flag rate in the Santa Cruz control, vs amplitude rebuild 8.0% and
optical UH 27.5%). The full four-way comparison is now printed in "The event and the
products", stated as flag rates only (no mechanism attributed to UH's failure).

**4. Timeliness × accuracy.**
Blocked on confirmed provider release dates for UH and LIST (register flag #7; our
ingest dates are upper bounds only). The provider e-mail should also ask for LIST's
methodology document (its radar/ResNet basis is provider-stated, not documented —
register flag #14) and UH's acquisition dates/scenes (vendor-level Vantor is
author-confirmed; per-scene attribution is not, which bounds how hard the RQ2o
"same vendor" comparison can be pushed).

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

Decided 2026-08-07 to keep content review separate from the language pass. Queued:

- **Scrub the DIY radar rebuild from the manuscript** (user decision): remove the Santa
  Cruz 8.0% clause from the coherence paragraph and the "tunable rebuild saturates"
  item from Results III (renumber that list); the experiment stays in the findings
  register (RQ6). Check the Santa Cruz control sentence still reads correctly with only
  the coherence 1.2%/0.9% vs optical 27.5% contrast.
- **Sweep for "documenting our own methodology corrections" tone**: the paper should
  state its rules positively, not narrate how we discovered them. Known instances: the
  Methods average-precision passage ("We never quote average precision for an individual
  product: … collapses to a formula … the derivation of why is in the Appendix") and its
  Results III sibling ("which should not be used to make this comparison at all…").
  Rewrite as brief positive statements of practice with an Appendix pointer.
- General content review (user, with fresh eyes once the language pass is done).

## Editorial / publishing

**5. Humanizer pass over `manuscript_v2.qmd` (in progress, iterative with review).**
Done: Abstract, Introduction, event/products, three-references (~iterations 1–2).
Remaining: Methods, Results I–V, Recommendations, Conclusion, Appendix (~170 em dashes
at last count, plus pattern fixes). Ground rules agreed: em dashes go; numeric-range en
dashes stay; technical terms keep their names with a plain gloss at first use; numbers,
crossrefs, math, code untouched; one section per iteration, user reviews each diff.
Manuscript only — deck explicitly out of scope for now.

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
