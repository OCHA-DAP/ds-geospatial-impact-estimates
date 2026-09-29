---
status: "accepted"
date: 2026-09-29
deciders: Z. Arno
---

# Precision and recall are anchored on opposite sides, so matching is not one-to-one

## Context and Problem Statement

Products flag buildings; the Copernicus EMS reference is a set of damage points. There is no
shared list of instances, so scores are computed by proximity at a radius r (ADR-0030 fixes the
frame as footprint distance on the shared Overture base, ADR-0025 the wider method).

Each metric is anchored on its own side. Precision asks, of the buildings a product flagged, how
many have a reference point within r. Recall asks, of the reference points, how many have a flag
within r. Nothing forces the two to agree on which pairs matched, and nothing stops one reference
point from validating several flagged buildings at once.

That matters here because buildings are packed tightly. In the core region the median distance
between neighbouring buildings is 9.6 m and 93% have a neighbour within 20 m, so a single damage
point commonly sits within the matching radius of more than one building:

| radius | expert damage points | distinct buildings they label damaged |
|---|---:|---:|
| 10 m | 1,467 | 2,064 |
| 20 m | 1,467 | 3,727 |

At the reporting radius each point licenses about 1.4 buildings. A product that flags the whole
cluster around one collapsed building is credited for the cluster.

## Decision Drivers

* Detection benchmarks in computer vision (PASCAL VOC, COCO) force a greedy one-to-one assignment,
  so a second detection on the same object is a false positive. Reviewers from that tradition will
  expect it.
* The brief states throughout that measured precision is a **lower** bound, because gaps in an
  incomplete reference turn correct flags into apparent false alarms. Non-injective matching pushes
  precision the other way, and only the first bias has been quantified.
* Recomputing every score under a one-to-one assignment would invalidate the frozen artefacts and
  every number in the brief and the scroll story.

## Considered Options

* Keep dual anchoring, disclose the direction of the bias.
* Re-score everything under greedy one-to-one assignment.
* Report both conventions side by side.

## Decision Outcome

Chosen: **keep dual anchoring and disclose it**, because the two metrics genuinely answer questions
with different denominators (of what a product shipped, how much was real; of the damage that
existed, how much was found), and because re-scoring would break the frozen record for a correction
whose size is not known.

The consequence is stated in the brief: the lower bound is the lower bound *under this convention*,
not the lowest conceivable one.

### Consequences

* Good: the two metrics keep their natural denominators, and nothing frozen has to be recomputed.
* Good: the direction of the bias is on the record rather than waiting to be found by a reviewer.
* Bad: F1 is not the harmonic mean of a single confusion matrix, since the true-positive count
  differs between the precision and recall sides. It is a composite and should be read as one.
* Bad: precision is biased upward by an unquantified amount, in dense built-up areas most of all.
* Open: the size of the effect is measurable. Re-scoring one product under greedy assignment at
  10 m would bound it, and has not been done.

## More Information

The brief's main text carries one clause on this, in the sentence that introduces the baseline
reference as the strictest definition used in the study. The appendix carried a fuller version
until 2026-09-29, when it was cut for length; this record is where it lives now.

Related: ADR-0025 (evaluation method), ADR-0030 (footprint frame and the Microsoft one-to-one
footprint mapping, which is a different one-to-one question), ADR-0031 (crowd credit measured, not
extrapolated).
