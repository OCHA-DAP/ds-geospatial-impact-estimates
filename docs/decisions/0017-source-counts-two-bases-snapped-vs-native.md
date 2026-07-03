---
status: "accepted"
date: 2026-07-03
deciders: zackarno
---

# Report source damage counts on two bases: Overture-snapped for comparison, native for attribution

## Context and Problem Statement

`harmonize_common` projects every source's damage onto a shared **Overture base**
(nearest footprint within 20 m) so the viewer can compare sources apples-to-apples.
But a source's **native** building count and its count of **distinct Overture
buildings flagged** are not the same number: fine footprints collapse onto shared
Overture buildings during the snap. Measured
([exploratory/0003](../../exploratory/0003-overture-snap-granularity/findings.md)):

| Source | Native | Overture-snapped | Gap |
|---|---|---|---|
| Microsoft (footprints ≈ Overture) | 8,410 | 8,342 | −1% |
| CEMS (per-building points) | 3,072 | 2,708 | −12% |
| **UNEP debris (fine GBA polygons)** | **96,046** | **75,656** | **−21%** |

The gap is a **footprint-granularity artifact** (collapse, not missing damage — 98%
of debris still land on an Overture building), and it is large for the incoming UNEP
debris source. So: **which count do we report** — UNEP's own 96,046, or the
Overture-snapped 75,656?

## Decision Drivers

* Cross-source comparison must stay apples-to-apples (one basis for all sources).
* Attribution must be faithful to a provider's own published figure.
* The distinction must not silently vanish — a future reader must be able to see it.
* Low stakes here: debris has **no analysed extent → no damage fraction** (no
  denominator to amplify the gap into a wrong rate).

## Considered Options

1. **Report the Overture-snapped count everywhere** (75,656).
2. **Report the native count everywhere** (96,046).
3. **Two bases by context** — snapped for comparison, native for attribution, both labelled.

## Decision Outcome

Chosen option: **"Two bases by context"** — the standing rule is
**compare on the base; attribute on the native base:**

* **Comparison contexts** — agreement/Venn view, Overture-view building highlights,
  any cross-source count/metric → **Overture-snapped** (the same basis every source
  is counted on).
* **Attribution contexts** — native view, the source's headline card, exports, "what
  the provider reports" → **native authoritative**.
* **Label the basis wherever a number appears.** The UNEP debris hover shows both:
  `Damaged buildings: {native} (Overture-snapped: {snapped})`, so the detail is
  carried inline and doesn't get lost later.

This is a general method, not a debris special-case: it retroactively fits Microsoft
(−1%) and CEMS (−12%), which simply had gaps small enough that no one noticed. Apply
it to any future source whose native footprints differ in granularity from Overture.

### Consequences

* Good, because comparison stays fair *and* we never misrepresent a provider's own
  headline; the granularity gap is explicit rather than a silent discrepancy.
* Good, because it generalises — the next fine-footprint source is already covered.
* Bad, because every source now carries two numbers that must be labelled; drop a
  label and a reader could conflate them (mitigated by the dual-number hover).
* Neutral, because the interim gap is only consequential for *counts*; the moment a
  source needs a **damage fraction**, the basis choice becomes load-bearing and this
  ADR should be revisited (debris avoids it by having no fraction — see below).

## Pros and Cons of the Options

### Report snapped everywhere

* Good, because trivially comparable across sources.
* Bad, because it tells the world UNEP found 75,656 when they published 96,046 —
  we would be misrepresenting their data by an artifact of *our* base choice.

### Report native everywhere

* Good, because faithful to each provider.
* Bad, because in the comparison view debris would read ~27% higher than Microsoft/
  CEMS purely because GBA footprints are finer — apples-to-oranges.

## More Information

Evidence + method (incl. the cache-integrity guard that this analysis exposed):
[exploratory/0003-overture-snap-granularity](../../exploratory/0003-overture-snap-granularity/findings.md).
The Overture-base snap itself lives in `pipelines/harmonize_common.py` (`SNAP_M = 20`).
Revisit if/when a source that snaps with a material gap needs a damage *fraction*.
