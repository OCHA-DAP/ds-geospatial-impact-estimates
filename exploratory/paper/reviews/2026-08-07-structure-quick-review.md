# Structural quick review — academic-paper-reviewer plugin (quick mode), 2026-08-07

Reviewer persona (Phase 0 field analyst): "Dr. Elena Marchetti", Associate Editor,
Q1 applied disaster-science journal (IJDRR/NHESS type), ex-CEMS validation scientist;
structure-and-organization focus per the authors' instruction. Manuscript state:
commit 9333957 (post language pass, post clarity batch 1). Scope exclusions: citation
formatting, hedging conventions themselves, pending analyses (CIs, timeliness).

Venue-fit assessment (field analyst): Q1–Q2 in applied disaster/remote sensing;
example venues IJDRR, NHESS; Disasters (ODI) if pitched to practice. Maturity: solid
draft approaching near-submission, one analysis cycle short (CIs, timeliness).

## Quick assessment (verbatim)

The right material is here — nearly all of it — but the paper's single most important
comparison is scattered and its second Results section is doing two jobs under one
misleading title. The prose within any given block is disciplined, the Appendix boundary
is drawn almost exactly right, and the Methods treatment of the matching radius is a
model of anticipating misreading. What fails is macro-navigation. First: "Results II:
testing the reference itself" spends its second half on the per-AOI scorecard, the
as-delivered precision list, and the as-delivered geography-null benchmark —
product-performance material, including arguably the paper's headline negative finding
("four of six matched or beaten"), filed under a reference-audit heading where no reader
will look for it. Second: the products-versus-geography comparison is smeared across
Results I (rank ρ, two tables), Results II (matched-list precision/recall), and Results
III (best-F1, point-vs-curve), under three metrics, and the reader must assemble the
paper's central claim unaided until the Conclusion does it for them. Third: the
Discussion introduces two previously unreported empirical results with no methods
anchor. The hindsight hedge on the null model, while individually well-written every
time, appears in roughly seven locations and needs a designated anchor. These are
reorganization problems, not rewriting problems: a desk-revise, not a rebuild.

## Key issues (condensed; severity · confidence)

1. **Results II is two sections wearing one title** (Critical · 5). Second half
   (per-AOI scorecard, as-delivered list, dead-zone mechanisms, as-delivered null
   benchmark) is product performance filed under "testing the reference itself". Fix:
   split — reference audit stays Results II; the scorecard-in-both-frames block moves
   to follow it (or tails Results I).
2. **The geography-null comparison has no home** (Critical · 4). Central claim
   assembled across three sections, three metrics (rank ρ / matched-list P-R / best-F1);
   only the Conclusion unifies it. Fix: consolidate single-product-vs-null into one
   subsection + summary table (frame × metric × products-beating-null); Results III
   then does one job (agreement/fusion).
3. **Discussion introduces new results with no methods anchor** (Major · 5). The
   fifteen-combination self-diagnosis null and the 78–86% scattered-error result appear
   first in Discussion, no upstream method/figure. Fix: promote to a short Results
   subsection (a paragraph of method each) or label as register-documented auxiliary
   analyses at first mention.
4. **Frame declaration made, revoked, patched at a distance** (Major · 4). "Rest of
   the paper quotes best-case unless labeled" (Results I) is undermined in Results II;
   the "Results III inherits best-case flattery" caveat lives in Results II. Fix:
   define both spatial frames beside @tbl-allframes in Methods (extend the existing
   device); move the flattery caveat into sec-dial beside @tbl-dial.
5. **Methods sec-dayzero overgrown with interpretation duplicated in Limitations and
   Appendix** (Major · 4). The fairness argument runs at full length in three places.
   Fix: Methods keeps construction + naming paragraph + ONE hindsight summary sentence
   with pointers; cut the "Two questions of fairness" paragraphs to that sentence.
6. **Null-is-hindsight hedge recurs ~7 times without an anchor** (Major · 4). Fix:
   anchor twice (Methods naming paragraph, Limitations); everywhere else a subordinate
   clause + crossref. Results I's two full repetitions go first.
7. **Crowd re-vote stability result told in full twice** (Minor · 5). Methods version
   collapses to one sentence (13.2% → 11.5% + @fig-crowdmech pointer); Appendix keeps
   the narrative.
8. **The DIY radar rebuild is a seventh product introduced mid-Results-list** (Minor ·
   4). Absent from Methods/@tbl-products, resurfaces in the sensing appendix as if
   established. Fix: two construction sentences in Methods or the sensing appendix +
   forward pointer. [NOTE: intersects the queued user decision to SCRUB the rebuild
   from the manuscript entirely — deletion resolves this issue.]
9. **Operational recommendation stated three times at near-full strength** (Minor ·
   4). Results III should end on arithmetic + pointer to Recommendations; Conclusion
   keeps one short echo.
10. **Introduction contribution 1 maps to no single section** (Minor · 3). After the
    Issue-1/2 restructure, add section references to all three contribution bullets.

## What to leave alone (verbatim highlights)

- Scorecard before reference audit (Results I → II): the pivot sentence is exactly
  right; audit-first would front-load reference minutiae.
- The Microsoft west-strip arc (teased Results I, resolved Results IV): a held mystery,
  not a held caveat; do not collapse.
- The Appendix boundary: nothing load-bearing hiding there; pointers carry the one
  number the main-text reader needs.
- The long Methods radius treatment: earns every line.
- Recommendations as a separate audience-labeled section: most navigable page in the
  paper.
