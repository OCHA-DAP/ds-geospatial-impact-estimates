# Appendix trim plan, 2026-09-28

Current: 9,394 prose words across 15 sections, about two thirds of the brief.
Target below: ~3,900, a 58% cut. Frozen first: `appendix-frozen-2026-09-28.qmd`
(source) and `appendix-rendered-2026-09-28.md` (numbers resolved), tag
`brief-appendix-frozen-2026-09-28`.

## Section budget

| # | Section | Now | Target | Verdict |
|---|---|---:|---:|---|
| 1 | The two reporting regions | 390 | 300 | keep, light trim |
| 2 | How complete is the expert reference? | 279 | 250 | keep |
| 3 | Matching products to references, in full | 1,523 | 650 | cut hard, repeats itself three times |
| 4 | Area ranking and error structure: method | 279 | 230 | keep |
| 5 | Combining products, adjudicating: method | 423 | 350 | keep, light trim |
| 6 | The geography benchmark: framing | 354 | 500 | keep, absorb the best of §7 |
| 7 | The geography null and fusion, in full | 1,156 | 0 | **delete** |
| 8 | Area-ranking detail: tables and error structure | 1,101 | 550 | cut the objection-rebuttals |
| 9 | Precision and recall in both frames, in full | 1,053 | 600 | cut the paired-percentage wall |
| 10 | The single-product ceiling: three experiments | 323 | 300 | keep |
| 11 | The west-strip case study, in full | 756 | 600 | keep, drop the closing sermon |
| 12 | A version postscript | 341 | 250 | keep |
| 13 | Performance versus matching radius | 360 | 300 | keep the table, trim prose |
| 14 | Confidence intervals | 217 | 200 | keep |
| 15 | How the crowd adjustment works | 839 | 550 | trim the re-vote narrative |

## The three big structural cuts

### 1. Delete §7 entirely, the duplicate benchmark section (−1,156)

Sections 6 and 7 are two accounts of the same model. Section 7 opens by explaining how
to read it alongside section 6:

> *How to read this section next to the previous one.* This section is adapted from the
> frozen v3 manuscript, where the benchmark was reported as a headline result and scored
> across everything each product delivered...

A section that needs an instruction manual for its relationship to the section above it
is a section that should not be there. It is imported from v3, scored in a different
frame, and admits both. Three things in it are worth keeping, folded into §6 in about
120 words:

- the output is a continuous risk score, so a product is one point against a whole curve;
- the hindsight cut, F1 moving under a blind nested cut rather than a hindsight one;
- the "null, not baseline, and not day zero" distinction, compressed to two sentences.

Everything else in §7 is already in §6 or in the v3 record, which is linked.

### 2. Section 3 says the same three things three times (−870)

The matching radius is justified in three separate places: the building-spacing
paragraph, then "The radius is not a tolerance applied to the products", then again in
§13. Pick one, the spacing argument, and cross-reference it.

The true-negatives point appears twice in adjacent paragraphs, once as "neither uses the
undamaged background (true negatives), so the size of that set affects no score" and
again as "precision and recall never use that count, so it affects no headline number".
One clause covers it.

"There is one matching rule and two labelled exceptions" then restates the two exceptions
the preceding paragraphs just explained, and adds a parenthetical distinguishing the 20 m
field radius from a different 20 m. That whole paragraph can go.

Also delete the centroid-frame paragraph. It narrates what an earlier draft of this
document did, which is what ADR-0030 is for, and the ADR is already cited.

### 3. Sections 8 and 9 argue with objections nobody raised (−1,000)

Section 8 spends about 200 words raising the count-versus-fraction objection and then
defeating it. Section 9 does the same with "shouldn't precision fall sharply outside the
one dense zone?". Both follow the same shape: state an objection in the voice of a
sceptic, then show it fails. One sentence each plus a pointer to the artefact does the
same work.

Section 9 also lists the flags-outside-Caraballeda share and precision lost for all six
products as paired percentages, twelve numbers in one sentence, to establish a single
claim: precision falls in proportion to where a product chose to flag. Keep the claim and
the diagonal, drop the enumeration, the figure carries it.

## AI language to strike

Empty topic sentences, the pattern you have flagged before:

- "Two questions of fairness follow from putting a fitted model beside an unfitted product."
- "Much of this case study generalizes."
- "Two further tests use the same cell lattice." and "The same cell lattice yields one further result."
- "That ambiguity applies to every number in this section, not just the anomaly. Everything above assumes CEMS is complete within its extents. The next section tests that assumption."

Staged objections and reveals:

- "A natural objection is that... and the objection fails"
- "That sounds alarming until one asks how much two small vote samples should agree even if volunteers were perfectly consistent, and the answer is: not much."
- "The sharper question is whether the products can out-rank geography *within* the damage zone, and there the result is different."
- "Splitting the product at the scene boundary shows what was hidden inside the headline number."

Dramatised comparatives and filler:

- "The dangerous alternative, errors that track urban form, is what the test rules out."
- "In short, the products over-call most where damage is worst."
- "which is worth remembering when reading any two products as 'different'"
- "so we test that directly" (twice)

Self-referential document provenance, which belongs in the decision records that are
already cited:

- "An earlier draft measured distance from each building's centre point instead..." (ADR-0030)
- "An earlier draft instead assumed the unreviewed flags contained damage at the same rate..." (ADR-0031)

Counted-list openers. Four sections open by announcing how many things follow: "Two
analyses relax that choice", "Two mechanisms explain", "Two further tests", "Three
independent experiments". Keep at most one.

## Two judgement calls for you

**The west-strip case study.** It is the best-written section here and the strongest
argument in the brief for metadata transparency. It is also 756 words of one product's
failure in an appendix, and Caleb is a reviewer. I would keep it and cut only the closing
"Much of this case study generalizes" paragraph, but the case for moving it out to its
own note is real.

**The crowd re-vote.** Sections 5 and 15 both explain the crowd adjustment. Section 15's
first half is the mechanism, which §5 already gives; its second half is the August re-vote,
which is new and worth keeping. Consider cutting §15 down to the re-vote alone and letting
§5 carry the mechanism.
