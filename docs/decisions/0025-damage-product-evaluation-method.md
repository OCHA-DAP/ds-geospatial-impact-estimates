---
status: "accepted"
date: 2026-07-31
deciders: Z. Arno, L. Milano
---

# How we evaluate rapid satellite building-damage products

## Context and Problem Statement

After the M7.5 Venezuela earthquake (24 June 2026) at least eight organisations released
building-damage products, and we had to answer a question responders were already asking:
which of these can we act on? The conventional approach is to score each product against a
single expert-interpreted reference — usually Copernicus EMS — treated as ground truth, and
report precision and recall.

Doing that here would have produced confidently wrong answers. The expert reference turned
out to capture 94% of field-reported *destroyed* buildings but only 49% of those reported as
*damaged*, so every precision measured against it is a floor rather than an estimate. We
needed an evaluation design that could say how wrong its own reference was, and that would
survive reuse on the next event rather than being tuned to this one.

## Decision Drivers

* The reference is incomplete in a way that is **correlated with the thing being measured**
  (both products and reference see destruction far better than damage), so its errors do not
  cancel.
* Products publish incompatible geometries (points, polygons, rasters) and different analysed
  extents, so there is no shared list of instances on which to build a single confusion matrix.
* A "good" score is meaningless without knowing what a *trivial* predictor scores on the same
  data.
* Whatever we conclude has to be defensible to the providers being evaluated, several of whom
  are partners.
* The method should be reusable on the next event by someone who was not involved in this one.

## Considered Options

* **A. Single expert reference, standard precision/recall.** The status quo.
* **B. Multiple references with non-overlapping blind spots, used separately.**
* **C. Fuse all references into one "best" ground truth, then score against it.**
* **D. Score only where all products and the reference overlap** (strict common region only).

## Decision Outcome

Chosen: **B — three references, each used only for the error type it can see, plus a
geography null model and an explicit measurement frame.**

The three references are Copernicus EMS (expert, building-level points — anchors both
precision and recall), MapSwipe (crowd review of AI-flagged cells — can judge false alarms
but never finds a miss, since volunteers only ever saw flagged places), and ChatMap (415
field reports — can prove a miss but cannot judge a false alarm, and has no survey frame).
Because their blind spots do not overlap, they can be turned on **each other**, which is how
we established that the expert reference is destruction-biased. Every precision is therefore
reported as an interval: a CEMS-measured floor and a crowd-adjudicated upper estimate.

Three further commitments fall out of this and are part of the decision:

1. **A hindsight geography null.** Coastline distance, building density and ShakeMap intensity
   are fitted to the event's own damage labels and used as a yardstick. It is *not* an
   operational alternative — fitting it needs the damage map a responder is waiting for — but
   without it "precision 0.08" has no interpretation. Report whichever learner (logistic or
   random forest) is stronger in a given frame, disclosing both, so the null is never
   accidentally weak and therefore flattering to the products.
2. **One matching radius, stated.** All CEMS-based numbers use 10 m proximity matching.
   Different radii change every number by 1.6–2.2×, so mixing them silently is the single
   easiest way to produce an incoherent result.
3. **No average precision for single products.** A product is one binary flag list; its AP
   evaluates to `P·R + (1−R)·π` and is not comparable to a continuous score's AP. Compare
   products at operating points, and reserve AP for continuous scores.

### Consequences

* Good: conclusions survive the reference being wrong, because the reference's own error is
  measured rather than assumed.
* Good: the null model makes "is this product any good" answerable rather than rhetorical.
* Good: reusable — the design needs one expert reference, any crowd or field signal, and three
  context rasters, none of which are Venezuela-specific.
* Bad: it needs three reference datasets, and a crowd campaign in particular may not exist for
  every event. With only an expert reference, precision remains an unqualified floor.
* Bad: the crowd reference is seeded from AI flags, so it scrutinises products unevenly and
  cannot be used as a building-level ground truth in its own right.
* Bad: more moving parts, and more ways to mix frames by accident — which is why the frame is
  now stated on every headline number.

## Pros and Cons of the Options

### A. Single expert reference

* Good, because it is standard, cheap and comparable to published work.
* Bad, because on this event it would have reported precision as an estimate when it was a
  floor, and would have had no way to discover the destruction bias at all.

### C. Fuse references into one ground truth

* Good, because it yields a single clean number per product.
* Bad, because the references measure different things at different geometries (50 m crowd
  cells vs building points); fusing them buries exactly the disagreement that is informative.
* Bad, because MapSwipe cells derive from AI flags, so fusing would let product output
  contaminate the ground truth.

### D. Strict common region only

* Good, because it is the fairest like-for-like comparison.
* Bad, because it evaluates products only where they all chose to look, which is their most
  favourable subset. We report it as the "best case" alongside as-delivered, rather than alone.

## More Information

Method and results: `exploratory/paper/manuscript_v2.qmd`; running record of every analysis,
including negative and superseded results, in `exploratory/paper/findings.qmd`. Supersedes
nothing; the frames and null-model conventions here are what later evaluations should follow.
