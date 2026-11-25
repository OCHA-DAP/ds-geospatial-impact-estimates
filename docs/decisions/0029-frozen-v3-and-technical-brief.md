---
status: "accepted"
date: 2026-09-02
deciders: Z. Arno (with L. Milano's review comments as input)
---

# Freeze manuscript v3; derive a technical brief as a separate living document

## Context and problem statement

External review (L. Milano) repeatedly flagged the geography-null and weighted-fusion
material as overweighting an already complicated paper for the audience we now want to
reach. At the same time, that material is the manuscript's methodological spine and the
review threads (Hypothesis annotations) anchor to the published v3 text and URL. A
professional writer will later produce the public-facing summary from whatever we hand
them. We needed to decide how to serve both audiences without doubling maintenance.

## Considered options

1. **One evolving paper**: keep editing v3 toward the lighter framing. Rejected: the
   null/fusion apparatus is load-bearing for the technical record (it is what makes
   "products add little beyond geography" a demonstrated claim), and stripping it would
   orphan the review annotations and weaken the citable record.
2. **Hard fork**: copy v3 into a second document and edit both. Rejected: two living
   documents with hand-copied numbers is the maintenance trap; prose and figures drift.
3. **Frozen record + derived brief (chosen)**: v3 is frozen as the immutable technical
   record (errata only) at its existing URL, preserving Hypothesis anchors. A new,
   shorter *technical brief* — the backbone a writer will turn into the public summary —
   is built by subtraction at a new pages path.

## Decision

Option 3, with these rules:

- **v3 freeze**: tag in git; editors' note marks it frozen; only factual errata after.
  It keeps `pages/manuscript/` so review annotations stay anchored.
- **The brief** is organised strictly around the three coordinator questions. The
  geography null is demoted to two sentences ("a model of building density and terrain
  performs comparably", per the RQ8d ablation) plus an appendix pointer; weighted
  fusion appears once (one sentence, one bar in the best-F1 figure variant).
- **Numbers never fork**: both documents read the same frozen artefact CSVs; the brief
  hand-types nothing.
- **Figures never fork**: variants come from `--summary` flags on the existing figure
  scripts writing new suffixed PNGs (precedent: `--slides`); the v3 figures are never
  edited or overwritten, so reverting is a no-op.
- **Appendix imported whole** (amended 2026-09-02, same day): the brief carries v3's
  full appendix verbatim rather than a slim pointer set. Because v3 is frozen, the
  import is a one-time copy with no ongoing sync cost, and it makes the brief
  self-contained (journal-viable without a later import step). The brief-specific
  "geography benchmark" appendix section, with a TBD marker for reframing the
  benchmark comparison, fronts the imported material.

## Consequences

Good: review anchors and the citable record survive untouched; the writer gets a
decluttered backbone; maintenance concentrates in one living document; rollback is
trivial because nothing v3 depends on is modified. Bad: partners can now cite two
documents (mitigated by the brief pointing at v3 as the record); a journal submission
would need the appendix import later.
