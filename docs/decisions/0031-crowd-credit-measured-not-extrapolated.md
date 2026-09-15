---
status: "accepted"
date: 2026-09-10
deciders: zackarno
---
# Crowd-adjusted precision credits only reviewed-and-confirmed flags

## Context and Problem Statement

Precision against the Copernicus reference is a lower bound because the reference misses
damage. The paper adjusts it with the MapSwipe crowd: a flagged building with no Copernicus
point within 10 m is credited if the crowd judged its ~50 m cell damaged. The crowd never saw
every cell. Two conventions for the unseen flags existed side by side: the dial table
(`rq5b`), the as-delivered scorecard (`rq2i`), the bootstrap CIs (`rq9`) and the round-2
sensitivity (`rq7`) *extrapolated* the confirmed share among reviewed flags onto the
unreviewed ones; the bounds ladder (`rq2r`) and the scroll story credited nothing for them.
The two disagree wherever coverage is thin (IMPACT .277 vs .187 at 10 m; UH .423 vs .202) and
the brief had to explain the divergence in its crowd appendix.

## Decision Drivers

* The MapSwipe campaign was seeded on Microsoft's coastal-strip flags, so the reviewed flags
  of the other products are the ones that fell in Microsoft's zone, not a random sample.
  Extrapolating from them is an assumption the data cannot support.
* One convention everywhere: a reader should not meet two "crowd-adjusted" numbers for the
  same product.
* A bound should be a measurement.

## Considered Options

1. Extrapolate everywhere. Rejected: the representativeness assumption above; inflates UH
   from .20 to .42 on 27% coverage.
2. Keep both, state each where used (the status quo). Rejected: confusing, and the dial table
   carried the weaker convention.
3. Measured everywhere: credit only flags whose cell the crowd reviewed and judged damaged;
   state the crowd's coverage of each product's unmatched flags beside the value.

## Decision Outcome

Option 3. `rq5b`, `rq2i`, `rq9` and `rq7_round2` compute the measured value; the column is
renamed `P_crowd_adj` -> `P_crowd` so stale readers fail; `rq2r`'s extrapolated columns are
removed; the dial table shows coverage in parentheses for products. The extrapolated values
remain reproducible at tag `paper-frozen-v3-centroid` (pre-ADR-0030) and at the commits
before this one on branch `paper-polygon-frame`.

### Consequences

* Good: one number per product, no assumption about unseen flags, coverage visible.
* Bad: products the crowd barely reviewed (UH, IMPACT, LIST, OSU) show lower crowd-adjusted
  precision than before; the text says why.
* Neutral: Microsoft (99% coverage) is unchanged to three decimals.
