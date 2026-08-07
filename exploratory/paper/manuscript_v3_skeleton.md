# manuscript_v3 skeleton — deck-spined short paper (for approval)

Rule: v3 SUPERSEDES v2 (no fork). v3's appendix inherits v2's methods machinery and
appendix wholesale; v2 gets a superseded banner when v3 is approved; publish script and
README repoint then. Numbers only from frozen artefact CSVs. Prose harvested from the
deck and the humanized v2, not regenerated.

Target: main text ~3,500–4,500 words (v2 main text is ~13,700). Every results section
follows one pattern: takeaway, the one figure/table, 2–3 sentences of how, appendix
pointer.

---

## Title + Abstract
Reuse current abstract near-verbatim (already distilled, already edited by user).

## 1. Introduction (~1 page)
Context (responders' first-days window, product proliferation); what we did (six
products, three references with non-overlapping blind spots); the two contributions.
Close with the deck's reader contract, three questions: can a responder act on a single
flagged building; do the products at least rank neighbourhoods; what is the sensible way
to use them.

## 2. The event, the products, and the references (~1.5 pages)
Event paragraph (M7.5, 24 June 2026, EMSR884). Products table + extents map + timeline
figure (framed preliminary, as now). Three references and what each can/cannot see
(reference-architecture figure); which reference is used where, condensed; the
floor/ceiling rule stated ONCE here. Appendix pointers: sensing primer; matching rule
details.

## 3. Results (~5-6 pages, six subsections, one pattern)

### 3.1 Building-level precision does not support acting on single flags
Takeaway: as-delivered precision 0.009–0.081; in the best area 0.04–0.09 with recall
0.31–0.69; ten to twenty misses per hit even there. Figure: per-AOI scorecard. How: 10 m
proximity rule, two sentences; both reporting regions defined in two sentences.
Appendix: matching details, radius sensitivity.

### 3.2 A hindsight geography model matches the products
Takeaway: a three-variable model (coast, density, shaking) fitted after the fact sits
inside the product range everywhere we tested. Table: the null tally (frame × metric ×
outcome, from v2's @tbl-nulltally). Figure: best-F1 bars. How: three sentences (inputs,
hindsight fit, spatially blocked scoring). Appendix: construction, fairness, AP
degeneracy.

### 3.3 The expert reference is a floor, so every precision is an interval
Takeaway: CEMS captured 94% of destroyed but 49% of damaged buildings; crediting
crowd-confirmed damage lifts Microsoft 0.08 → ~0.24; ~11% of field-reported damage
escaped every product (inland gap). Figure: grade slope. How: three references turned on
each other, two sentences. Appendix: crowd mechanism + independent re-vote.

### 3.4 Area ranking works, and geography ranks about as well
Takeaway: at sector scale rank correlation ~0.54–0.59 and 80–85% of worst cells found
(usable); the same null out-ranks five of six pooled, splits 3–3 inside the damage zone:
the products know where within a zone, not which zone. Figure: priority map (or the
ranking table). How: two sentences (hex aggregation, rank correlation).

### 3.5 Agreement between independent products is the operating point
Takeaway: the count of agreeing products is a dial with a known price at every setting
(dial table: 26.5 → 0.8 visits per find); voting doubles the best single product's F1
(0.290 vs 0.148), gives up 18% to a fusion nobody could fit in time; the ingredient is
method independence (best pair optical×optical MS∧UH; worst the coherence twins).
Figures: dial table + pairwise frontier. Three honest caveats, compressed (equal trust;
count independent methods; k buys workload not hit rate). Appendix: fusion machinery.

### 3.6 One failure could be traced; five could not be examined
Takeaway (framed per the causal-framing flag: single scene is the established fact):
Microsoft's west-strip failure traced to a single scene via its published per-building
metadata + the crowd campaign; crowd rejected 71% there; UH on the same vendor flagged
3% (vendor-level check). Placed LAST and framed as what metadata transparency buys, not
as a headline contribution. Figure: west-cluster adjudication.

## 4. Summary and discussion (~1 page) [NEW section per user]
The three questions answered, one short paragraph each (no / yes-but-geography-ties /
count-agreement-between-independent-methods). Then the two negative results that fit no
single finding: reliability cannot be self-diagnosed from flag patterns (fifteen pairs,
all null); failures CAN be mapped where a reference exists (78–86% benign scatter,
trouble in pockets). Close: what transfers to the next event; Myanmar 2025 as the
replication candidate.

## 5. Recommendations (~0.5 page)
Reuse v2's audience-labelled section nearly as-is (responders / providers / evaluators).

## 6. Limitations (~0.5 page)
Reuse v2's six labelled caveats, lightly trimmed.

## Appendix (unlimited, inherited + expanded)
Everything from v2's appendix PLUS the Methods machinery v3's main text no longer
carries: dual-anchored matching (with figure), radius reasoning + 20 m sensitivity,
reporting regions, centroid-vs-native check, cloud-visibility check, null-model
construction (schematic) + learner table + threshold protection + event-information
layers + AP derivation, sensing primer, crowd-adjustment mechanism + round-2 re-test,
reproducibility note.

---

Open questions for approval:
1. Priority-map figure vs ranking table in 3.4 (deck uses the map; the map is more
   readable, the table more precise).
2. Does the west-strip section stay in Results (as 3.6) or move into the discussion?
   Recommendation: Results, last position, low billing.
3. Keep v2's "held mystery" tease of the west strip in 3.1, or let 3.6 stand alone?
   Recommendation: one pointer sentence in 3.1, nothing more.
