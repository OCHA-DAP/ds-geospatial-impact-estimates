# Brief annotation anchors, measured 2026-09-25 before the republish

Anchoring is by quoted text: an annotation survives whenever its quote still appears
in the render. Detached ones stay readable in Hypothesis as orphans; they are listed
here so the text they referred to is not lost.

## ven brief: CHD (internal) (`ppY7JE2k`): 10 anchored, 48 detached

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “Sections and captions state which region they use.”
  - note: this is awkward...say something more like: The core area is the main analysis scope used for the rest of the paper, but whenever it is unclear we refer to it as "core area/region or as-delivered" --- feel free to improve but you get what i mean

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “every predictor is scored alike, and each product’s favourable case (it holds 96% of the expert-recorded damage).”
  - note: every predictor sounds weird.... would be better to say : "one shared area where each product can be compared against all the others." The part about the favourable case might not make sense here or it's awkward also the reader does not know about all the FPs so they dont know it would be most favourable yet... its a good point, but idk if it's awkward or what here?

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “As delivered scores each product across everything it shipped, wherever the expert reference mapped.”
  - note: Change to: "As delivered evaluates each product across the entire geographical it delivered where it overlaps with our reference data."

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “Figure 1: Who analysed where. Each product’s analysed extent, the five expert-mapped CEMS AOIs (dashed black), and, in red with the zoom frame below, the ~61 km² core region where the head-to-head and combination analyses live. UH publishes no extent (its polygon is derived from its own classified footprints); UNEP publishes none at all and is scored under a stated coverage assumption.”
  - note: change to: "Figure 1: Product & Analysis extent. Top shows each providers analysis extent as well as the reference CEMS AOIs. Bottom shows the area of overlap (red) where all products could be evaluated and compared against one another and the same reference. This red area is referred to as the core analysis area in the paper"

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “Table 1: Products evaluated, as delivered. Analysis scope: Overture base buildings and area inside the provider’s published extent. Damaged buildings flagged: the provider’s own count (its own footprints for Microsoft, UH and UNEP; base-building ids for IMPACT, OSU and LIST). OSU figures refer to its v0 delivery, the version available during the response. UNEP publishes no extent and is scored under a stated coverage assumption. Sensor and resolution are as stated by the provider or visible in the delivery; “not stated” marks the products for which neither applies.”
  - note: too much info here. Also we're introducing "as delivered" terminology probably before defining it. Can we just say title:Table 1. Damage Products Evaluated The only part that could potentially be retained is the part about the overture footprint from analysis scope.... could this go under as footnote or something?... whats with the provider names all the way to the left? They are more standardized under Provider. a way to combine them just as one column instead of two?

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “Each published an analysed extent, the area it actually examined; without one, “no flag” cannot be distinguished from “never looked”, so neither misses nor false alarms can be counted fairly.”
  - note: do we need this justification here? Maybe we could just say something like a few products were excluded which had no accompanying AOI or there area of analysis was so small it would have limited power of analysis.... steal wording from scrolly story (maybe a footnote there somewhere)?

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “against three references with complementary blind spots: expert damage points (Copernicus EMS), a crowd review of AI-flagged locations (MapSwipe), and 415 field reports (ChatMap).”
  - note: against a reference data set comprised of three sources:

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “could be defined or defended against three references with complementary blind spots: expert damage points (Copernicus EMS), a crowd review of AI-flagged locations (MapSwipe), and 415 field reports (ChatMap).”
  - note: perhaps too much detail for abstract. Can just say something like: "We evaluated 6 damage classification products that were published and available in the first n days of the earth quake response." (similar to below).

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “Six satellite damage products, one earthquake:”
  - note: take name from scrolly story v3... then say "Technical Brief" afteer

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “After the M7.5 earthquake that struck coastal Venezuela on 24 June 2026, at least eight organisations released satellite-derived building-damage products.”
  - note: we can rephrase we don't have to say 8 organizations we can just say something about the great number (vague) of products as there were more than 8 products and 8 orgs some were not even considered

- **zachary_arno_un_ocha**, 2026-09-24 — detached
  - quote: “a defined or defensible analysed extent, the area the product actually examined (Table 1): without one, “no flag” cannot be distinguished from “never looked”, so neither misses nor false alarms can be counted fairly.”
  - note: this is a bit vague. We can say "We evaluate 6 damage classification products that were published and available in the first n days of the earth quake response."

- **tristandowning**, 2026-09-09 — detached
  - quote: “a crowd campaign rejected 71% of one zone’s flags within days”
  - note: 71% is the share of majority-No *cells* (3,462 MapSwipe hexes), not of flags (RQ7 notes). Flags per cell vary, so the flag-weighted share may differ. "71% of the flagged locations" (as the appendix says) is the accurate wording; the recommendations and the west-strip appendix use "flags" and "reviews" loosely ("rejected by 72% of crowd reviews").

- **tristandowning**, 2026-09-09 — detached
  - quote: “The median distance between neighbouring building centroids in the core region is 9.7 m, and 93% of buildings have a neighbour within 20 m.”
  - note: Asserted in the `rq2f_vicinity.py` docstring and the findings register, but no script computes and no CSV stores these two values. Since the 10 m radius is the single most consequential choice in the paper, its justification should be a frozen artefact.

- **tristandowning**, 2026-09-09 — detached
  - quote: “96% of all CEMS damage points are in the first column”
  - note: Two small problems. The first column of the per-AOI heat map is "ALL (as delivered)"; Caraballeda is the second. And within the analysed extents Caraballeda holds 1,468 of 1,514 points = **97%**; 96% only holds against all 1,536 latest damaged/destroyed points including 22 that fall outside every extent. The same 96%/97% ambiguity applies to "it holds 96% of the expert-recorded damage" in Section 1 (1,467/1,514 = 97%). Pick a denominator and state it once.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Region: within the CEMS-analysed extents; reference: field reports (20 m GPS tolerance).”
  - note: Caption misdescribes the region. In `rq2_chatmap_recall.py` each product is scored within its *own* analysed extent (n = 376 / 415 / 415 / 388 field points), only the CEMS line uses the CEMS extent (381), and the UNEP and union lines use the core region (367). So the lines are not on one common region. Also the caption says "each line is one dataset" but the figure carries an eighth line, "union of six products" (0.97 → 0.87), which the text later uses for the "missed by everything" claim; describe it.

- **tristandowning**, 2026-09-09 — detached
  - quote: “about 11% of field-reported damage points”
  - note: The freeze log records 40 of 415 eligible field points with no product flag within 20 m = **9.6%** ("~40 (11%)" in the notes is the stale rounding). And the check ran over the five extent products only, UNEP excluded, so "no flag from any product" is slightly stronger than what was computed. Suggest "about one in ten (40 of 415)… from any of the five extent-publishing products".

- **tristandowning**, 2026-09-09 — detached
  - quote: “Even at the upper bound every product stays below 0.28.”
  - note: True under the *measured* crowd convention (`rq2r_precision_bounds.csv` P_upper max 0.279, Microsoft), and only just. Under the paper's *other* crowd convention, the extrapolated one used in the voting table (unreviewed cells assumed damaged at the reviewed rate), the same CSV gives P_upper_extrap UH **0.425**, IMPACT 0.293, UNEP 0.291. The abstract's "most generous defensible reading still leaves every product below 0.28" therefore depends on choosing the less generous of the two conventions the document itself uses. Say "under the measured-crowd convention" here and in the abstract, or report both.

- **tristandowning**, 2026-09-09 — detached
  - quote: “22,954”
  - note: **Table 1 flag counts are stale and on mixed bases.** IMPACT 22,954 and OSU 31,259 trace only to the first-pass RQ5 notes (2026-07-07, pre-freeze, "scored on their own full region"); the frozen as-delivered scorecard (`rq2i_per_aoi_scorecard.csv`) gives **23,491 / 32,643**. Microsoft 8,410 and UNEP 96,046 are *native* provider counts (DATA_MAP), although the footnote says all flags are "as mapped onto the shared building-footprint base" (gold-base Microsoft as-delivered = 9,217). UH "~91k" is unsourced; the UH containment validation records 80,913 → 76,378 after dedup. LIST 163,225 appears in no artefact. Since ADR-0029 says the brief hand-types nothing, this table should be generated from `rq2i` (or the footnote must say which basis each row uses).

- **tristandowning**, 2026-09-09 — detached
  - quote: “The single-scene west flags 28.7% of its buildings, with precision 0.05 and F1 0.10. The multi-scene east flags 7.6%, with precision 0.21 and F1 0.30”
  - note: **Two incompatible sets of west/east numbers for the same product and the same split, in adjacent paragraphs.** These (28.7% / 0.05 / 0.10 and 7.6% / 0.21 / 0.30) come from the pre-freeze RQ2d addendum in NOTES.md (2026-07-17, native Microsoft delivery, no CSV). The next paragraph quotes the frozen `rq2o_uh_west_strip.csv`: Microsoft west 32.4% at P 0.033, east 9.8% at 0.137. Same scene boundary (lon −67.03). Use the frozen numbers or state why the two bases differ.

- **tristandowning**, 2026-09-09 — detached
  - quote: “in practice they agree to within 0.005 in precision for every product”
  - note: **The two-implementation table looks like a rounding artefact, not a measurement.** No frozen CSV holds a six-product native-geometry scorecard at 10 m. Every "scorecard (native geometry)" value in the table (0.090 / 0.090 / 0.080 / 0.070 / 0.060 / 0.040) is exactly the centroid value (0.093 / 0.086 / 0.081 / 0.069 / 0.057 / 0.045) rounded to two decimals, and each "difference" equals the rounding residual. Those 2-dp values match `product_scorecard.csv`, which OPEN-ITEMS §7 describes as hand-assembled and stale. The one frozen *native* measurement that exists (`rq2_points_summary.csv`, Microsoft: P 0.121 on 8,023 native flags vs 0.081 on 9,138 gold-centroid flags, same 1,467 CEMS points) shows a 0.04 gap, not 0.001. Either produce the native-geometry run for all six and freeze it, or remove the "within 0.005" claim and this table. (Related: the ceiling appendix attributes Microsoft's higher confidence-curve baseline to "its own analysed region", but that region has the identical 1,467 reference points; the gap is geometry/delivery version, not region.)

- **tristandowning**, 2026-09-09 — detached
  - quote: “roughly 0.74 km² and 5.2 km²”
  - note: These are global H3 mean areas. At Caraballeda's latitude (10.6 N) `h3.cell_area` gives res 7 = 4.46 km², res 8 = 0.64 km², res 9 = 0.091 km². Two-decimal "0.74" implies a precision the number lacks, and the document then uses "~0.7", "~0.74", "~5", "~5.2" and "~0.1"/"~0.11" for the same three grids in different places (the values are hard-coded separately in `rq3h_agreement_ranking_fig.py`, `rq3g_frac_ranking.py`, `rq3f_null_ranking_both_fig.py`). Suggest "~0.7 km² (H3 res 8)", "~5 km² (res 7)", "~0.1 km² (res 9)" everywhere, and name the resolution once so readers can look it up.

- **tristandowning**, 2026-09-09 — detached
  - quote: “building density alone already falls inside the product band”
  - note: Density-only F1 is 0.086 vs OSU's 0.085 (`rq8d_null_ablation.csv`): inside the band by 0.001. "At the bottom of the band" is the honest phrasing. Also, rq8d's "paper" arm is a rq3f-pipeline refit (0.127) while the headline null elsewhere is rq8's 0.128; say which the "slightly stronger" DEM variant (0.143) is being compared with.

- **tristandowning**, 2026-09-09 — detached
  - quote: “from 1.8× to 2.3× the best single product”
  - note: 1.8× is the 20 m fusion ratio (0.386/0.212); at 30 m, the radius the preceding sentence is about, the ratio is 1.47× (0.427/0.291). And at 10 m the ratio depends on frame: 0.343/0.148 = 2.3× (fusion) or 0.290/0.148 = 2.0× (voting). State which predictor and radius each end of the range refers to.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Microsoft’s falls from 0.237 to 0.223, UNEP’s from 0.074 to 0.043”
  - note: These are *as-delivered* crowd-adjusted precisions (rq2i / `rq7_round2_padj_sensitivity.csv`), whereas the voting table's crowd-adjusted column is the *core* region (Microsoft 0.242, UNEP 0.253). A reader cross-checking against the table two sections up sees different numbers with no frame tag. Also note `rq5b_six_member.csv` has no crowd-coverage column, so the 6-of-6 crowd-adjusted 0.932 rests on an unknown reviewed fraction of its 77 unmatched flags (known open item).

- **tristandowning**, 2026-09-09 — detached
  - quote: “A statistically fitted combination of the six products scores about 18% higher on F1”
  - note: 0.343 / 0.290 = 1.18 uses rq8's voting best cut (building-label frame). Against the voting table's 5-of-6 F1 (0.276, point-anchored) it is 24%. More important: both green bars in the figure are **oracle operating points**: `best_f1()` in `rq8_learned_fusion.py` picks the F1-maximising threshold on the pooled out-of-fold scores. The nested-threshold bias check (`rq8_threshold_bias_r10.csv`) was run only for the geography null (0.1287 vs 0.128), never for the 15-feature fusion, whose score is far more threshold-selectable. Also "voting at its best cut 0.290/0.342/0.364" in the appendix silently changes rule across radii (k = 5, 4, 3). Suggest saying "at its best cut, chosen with hindsight" in the main text and running the nested check for the fusion.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Counting possibly damaged roughly doubles the reference and lifts every precision by 1.6–2×, singles and voting rules alike”
  - note: From `rq8c_basis_pr_r10.csv` the incl-possibly / paper-basis precision ratios are UH 1.43×, weighted fusion 1.42× and **flat voting 1.35×**; the full range is 1.35–1.96×, not 1.6–2×, and the composites move noticeably less than the singles. Related overstatements in this paragraph: (a) "No comparison reverses" is true for precision (what the figure shows) but not for F1: flat voting beats fusion under *Destroyed only* (0.318 vs 0.306) and loses at the paper basis; UH (0.175) and UNEP (0.193) fall *below* the logistic null (0.206) under incl-possibly after sitting above it. (b) "~3–4× precision margin" is 3.4× / 3.2× / 2.9× across the three bases, so "~3×". (c) "grade-neutral products gain" recall: every predictor's recall falls under incl-possibly because the denominator doubles; none gains.

- **tristandowning**, 2026-09-09 — detached
  - quote: “at 20 m the identical CEMS points label 2,733 core-region buildings damaged; at 10 m, 1,350”
  - note: The frozen CSVs (`rq8c_basis_pr_r10.csv`, `rq8b_asdelivered_baseline_r10.csv`) give n_pos = **1,348** at 10 m, not 1,350; and 2,733 appears in no frozen CSV (`rq8_best_f1_r20.csv` has no n_pos column). Minor, but these are stated counts; same pair is repeated in the radius appendix.

- **tristandowning**, 2026-09-09 — detached
  - quote: “no correlation between the pattern signals (flag rate, clustering, agreement with other products) and measured reliability was statistically distinguishable from zero”
  - note: **Unsourced in the frozen artefacts, and one test contradicts it.** `rq3e_reference_free.py` only prints the Spearman tests; the CSV stores inputs. Recomputing from `rq3e_reference_free.csv` (n = 15): every signal vs *precision* has p ≥ 0.29, but Moran's I of flags vs *lift* gives ρ = −0.59, p = 0.033. The sentence holds only if "reliability" means precision alone, which it does not say. Either define reliability as precision here or drop the claim; and freeze the test statistics to a CSV so the number is auditable.

- **tristandowning**, 2026-09-09 — detached
  - quote: “The null ranks fractions about as well as it ranks counts (ρ 0.43–0.65)”
  - note: `rq3g_frac_vs_count.csv` `rho_null_frac` runs **0.35–0.65** (min 0.350 for OSU at res 7), not 0.43–0.65; the count-null range is 0.445–0.701, so "about as well" also understates the drop for OSU. The IMPACT 0.29→0.46 and Microsoft 0.47→0.37 values and "only OSU beats its null under either target" are verified.

- **tristandowning**, 2026-09-09 — detached
  - quote: “78–86% of each product’s territory shows errors scattered at random”
  - note: **Does not match `rq3d_lisa_summary.csv`.** Share of non-significant cells: MS 81.4%, IMPACT 84.5%, OSU 87.5%, UH 85.0%, LIST 86.4%, UNEP 84.2% → **81–88%** (or 84–89% if outliers are counted as non-clustered). No definition reproduces 78–86. Inherited from findings.qmd / v3.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Moran’s I 0.45–0.60, p = 0.001”
  - note: **Does not match the frozen CSV.** `rq3_error_structure_summary.csv` (exposure spec) gives Moran's I at res 8: Microsoft 0.540, IMPACT 0.432, OSU 0.494; at res 7: 0.539 / 0.576 / 0.434. So the range is **0.43–0.54** (res 8) or **0.43–0.58** (both scales). The 0.45–0.60 range is from the 2026-07-07 NOTES.md table (131/689/903 cells, before the CEMS `is_latest` fix; the frozen CSV has 140/743/957 cells). p = 0.001 is verified. Same stale range sits in v3 and findings.qmd, so fix all three.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Microsoft’s precision is 0.080 at 10 m”
  - note: Microsoft's core precision appears as 0.081 (Section 2 as-delivered list, the best-F1 figure, the bounds ladder) and as 0.080 here and in the two-implementation table. The appendix explains this is native-geometry vs centroid matching, but the main text never says which frame it is quoting when it writes "0.045–0.093" (those are the centroid-frame values; the native-geometry scorecard gives 0.040–0.090). Suggest one sentence in Section 2 naming the frame, or standardising the main text on one set.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Comparing performance measurements of all products against each other and the derived combined products.”
  - note: Caption wording is clunky ("comparing performance measurements … against each other and the derived combined products"). Suggest: "F1 at each predictor's operating point: the six products (grey) and the two combinations (green), with precision and recall in brackets." Also state here that the combinations are shown at their *best* cut chosen on the same data, which is the fairness caveat the appendix discusses; the current "optimal performance weighting/configuration" phrasing hides that.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Unlike a fitted model, counting requires no weights, no training data and no reference, so it can be done as soon as the second product arrives.”
  - note: Two qualifications are missing here. (1) Choosing *which* threshold to act on is not reference-free: the "better agreement thresholds" (3- to 5-of-6) were identified in this study by scoring against CEMS after the fact; a responder on day 3 has no way to know that 5-of-6 rather than 2-of-6 is where the value lies, beyond the workload logic you give in the next paragraph. (2) With only two products the evidence here is weak: the best pair reached P ≈ 0.37 and the same-sensor pair 0.088, so "as soon as the second product arrives" oversells what k-of-2 buys. Suggest "as soon as *several* products are in hand" and an explicit sentence that the threshold is a workload dial whose hit rate was only knowable in hindsight.

- **tristandowning**, 2026-09-09 — detached
  - quote: “447,263 incl. intact”
  - note: The "Analysed buildings" column mixes units: Microsoft = footprints incl. intact, IMPACT/OSU = swath *area*, UH = buildings incl. intact, LIST = a building count with no intact/damaged qualifier, UNEP = "no extent". And in the "Damage flags" column LIST alone is given "in core region" while the other five are total delivered flags. The footnote does not cover either inconsistency. Suggest two columns ("analysed extent, km²" and "buildings on shared base") and one consistent flag basis.

- **tristandowning**, 2026-09-09 — detached
  - quote: “(the threshold-selection mechanics are in the Appendix)”
  - note: Dangling pointer inherited from v3: this *is* the appendix, and the brief's appendix does not contain the threshold-selection mechanics (how the best cut is chosen for the null and fusion, and whether it is chosen on the held-out fold). Same issue with "repeated at 20 m it is the same four products, in the same direction (Appendix)" and "plotted in the longer-form draft" further down. Either import those passages or point explicitly to the v3 record.

- **tristandowning**, 2026-09-09 — detached
  - quote: “The same test restricted to the Caraballeda AOI, ~0.7 km² cells.”
  - note: **This table uses a frame the brief says it never uses.** The reporting-regions table states results come in exactly two regions (core, as delivered), and the project's OPEN-ITEMS records the Caraballeda AOI being *retired* as a comparison frame on 2026-08-07 because it kept causing confusion. Yet this imported v3 appendix section still reports the within-damage-zone ranking on the Caraballeda AOI (LIST 0.668, OSU 0.642, IMPACT 0.548, nulls 0.456–0.597), while the main-text figure reports the *core-region* values for the same question (LIST 0.74, IMPACT 0.72, OSU 0.70). A reader now has two sets of "within the damage zone" correlations that differ by 0.06–0.17 and no sentence reconciling them. Meanwhile the core-region null value (0.648 at res 8, per `rq3f_null_ranking_core.csv`), the number the main text's ranking section actually rests on, appears nowhere in the brief. Suggest replacing this table with the core-region run (`rq3f_null_ranking_core.csv`) and deleting the "~0.1 km² three–three split" sentence unless it too has a core-region artefact. Note also that in the core frame the split is 3–3 at res 8 but **4–2 at res 9** (Microsoft 0.481 vs null 0.478, per `rq3f_null_ranking_core.csv`), so "the same three–three split holds at ~0.1 km²" is true only in the retired frame.

- **tristandowning**, 2026-09-09 — detached
  - quote: “TBD: the framing of the benchmark comparison is being reworked for this document”
  - note: A **TBD** marker is live in the published brief (the encrypted `content.enc` was rebuilt after this text was added). Since the passphrase is shared with providers, this reads as an unfinished document. Either finish the paragraph or cut it: the two sentences before it already carry the brief's position on the benchmark.

- **tristandowning**, 2026-09-09 — detached
  - quote: “ranking neighbourhoods by agreement beats every single product’s ranking (at both cell sizes tested)”
  - note: True only for the middle thresholds. At ~0.74 km² the 1-of-6 and 6-of-6 rules (ρ 0.62) fall *below* LIST (0.74), IMPACT (0.72) and OSU (0.70); at ~0.11 km² only 3-of-6 and 4-of-6 beat LIST. Suggest "ranking by three- or four-product agreement beats…" as the main text already says in Section 3.

- **tristandowning**, 2026-09-09 — detached
  - quote: “the best products correctly identify most of the twenty worst-hit cells”
  - note: **Only one product does.** In the agreement-ranking figure the top-20 overlap for single products at ~0.74 km² is LIST 0.65 (13 of 20); every other product is at or below 0.45 (9 of 20), and Microsoft is 0.35. So "the best product" (singular) identifies most; "the best products" do not. At the finer scale even LIST gets 4 of 20.

- **tristandowning**, 2026-09-09 — detached
  - quote: “the correlations spread from −0.09 to 0.59 at the ~5 km² cell scale”
  - note: Figure shows Microsoft at **0.58**; the CSV value is 0.585 and the figure formats with `:.2f` (rounds to 0.58). Text says 0.59. Pick one (the appendix table also prints 0.585).

- **tristandowning**, 2026-09-09 — detached
  - quote: “The fifteen two-product rules.”
  - note: **Caption does not match the figure.** The regenerated figure (from `rq5b_six_member.csv`) plots **six** two-product rules (open circles), not fifteen, and only MS∧UH is labelled. The "pair sharing its entire method" that the caption's point depends on (IMPACT∧OSU, P 0.088 / R 0.43) is an unlabelled grey circle, so the reader cannot locate it. The figure's actual visual subject, the k-of-6 frontier with crowd-adjusted whiskers, is not mentioned in the caption at all. Suggest labelling all pairs (or at least IMPACT∧OSU) and rewriting the caption around what is drawn.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Weight the count toward independent methods”
  - note: **The recommendation to weight toward independent sensing methods rests on one pair, and the same figure contains the counter-example.** The evidence is that IMPACT∧OSU (both Sentinel-1 coherence) reaches only P 0.088. But the best two-product rule in the frontier figure is MS∧UH (P ≈ 0.37), and those two share a sensing modality (VHR optical + AI classifier). The analysis register itself notes that "modality diversity is a day-one heuristic that did not predict this event's ranking". The brief resolves this by defining "method" narrowly (same sensor *and* same physical quantity), but that definition is not stated in the main text, so a responder reading "products that share a sensing method err together" would down-weight MS+UH, the pair that performed best. Either state the narrow definition and the n = 1 basis, or soften to "pairs built on the same sensor and signal added the least in this event".

- **tristandowning**, 2026-09-09 — detached
  - quote: “where the better agreement thresholds roughly doubled the F1 of any product alone (0.26–0.28 against the best single product’s 0.15”
  - note: **Two different "best voting F1" values for the same claim.** Here (and in the abstract) the gain is 0.26–0.28 vs 0.15, sourced from the scorecard-frame voting table (rq5b: 5-of-6 F1 0.276). But the best-F1 figure just above, and the appendix radius section ("voting at its best cut 0.290/0.342/0.364"), give flat voting F1 = **0.290** vs best single 0.148, from the model frame (rq8), where the recall denominator differs (e.g. Microsoft R 0.552 in rq8 vs 0.474 in rq5b). Both are defensible, but the document should pick one frame for the headline ratio and footnote the other; as written a careful reader finds 0.28 and 0.29 for what looks like the same quantity, and "1.8× to 2.3×" in the appendix for what the abstract calls "roughly doubles". Separately, no interval supports "roughly doubles": rq9 computes paired differences only against the null, never rule-vs-best-single. Marginal 95% CIs overlap (5-of-6 0.195–0.343, 4-of-6 0.184–0.326, UH 0.089–0.207), and "ρ 0.78 against 0.74" has no CI at all. The bootstrap script already stores the shared cell draws, so a paired rule-minus-best-single interval is a small addition and would let the headline stand on its own.

- **tristandowning**, 2026-09-09 — detached
  - quote: “Flag every building any product marked and 97% of known damage is covered, but a field team following those flags would make 26 site visits for each damaged building it reached; require all six to agree and 93% of flags are correct but only 18% of the damage is covered.”
  - note: **Radii and frames are mixed inside this one sentence, and the prose never says so.** "97% covered" and "26 visits" are 30 m values (rq5b_six_member_r30: 1-of-6 R 0.973; visits 26.4). "18% covered" is also 30 m (6-of-6 R 0.184). But **"93% of flags are correct" matches no measured precision at any radius**: 6-of-6 is P 0.64 at 10 m and 0.967 at 30 m; 0.93 is the 10 m *crowd-adjusted* upper estimate (P_crowd_adj 0.932), which the appendix itself says is an upper bound, not a measurement. Every product recall quoted before this point is at 10 m (0.31–0.69), so a reader will take "97%" as agreement massively lifting recall when most of the jump is the radius (1-of-6 recall at 10 m is 0.77, visible in the frontier figure below). The README's conventions warn that mixing radii is "the single easiest way to produce an incoherent result". Suggest: "…97% of known damage is within 30 m of a flag… require all six to agree and 97% of flags are correct at that distance but only 18% of the damage is covered" (or the 10 m set: 64% / 9%, with 93% labelled crowd-adjusted).

- **tristandowning**, 2026-09-09 — detached
  - quote: “preceded about 40 seconds earlier by an M7.2, struck near Yumare”
  - note: **Please re-verify against the current USGS solution.** As of today the USGS FDSN event service gives: M7.5 `us6000t7zp` at 22:05:04 UTC, epicentre 10.596 N, −67.221 W, "20 km W of Catia La Mar"; M7.2 `us6000t7zc` at 22:04:32 UTC, 10.371 N, −68.556 W, "20 km E of San Felipe". That puts the M7.5 on the La Guaira coast (consistent with where the damage was), and the *M7.2* near Yumare/San Felipe, with a 32-second gap rather than ~40 s. USGS relocates events as solutions are revised, so the sentence may have been right when written, but as it stands it appears to attach the foreshock's location to the mainshock. Cite the USGS event IDs and the solution date either way.

- **tristandowning**, 2026-09-09 — detached
  - quote: “swath (~372 km²)”
  - note: **Wrong by two orders of magnitude.** The IMPACT v2 analysed extent is ~32,713 km² and OSU's ~41,463 km² (the extents-map legend in Fig. 1 and the analysis register both give these values; `DATA_MAP.md` gives the IMPACT swath as ~32,712 km²). The table has ~372 and ~471. Whatever these two numbers are (a CEMS-intersected area? a typo?), they contradict the figure two paragraphs later and have been carried unchanged since `manuscript_draft.qmd`. If they are meant to be something other than the analysed extent, the column header needs to say so.

- **tristandowning**, 2026-09-09 — detached
  - quote: “We evaluated the six that published an analysed extent”
  - note: **Internal contradiction.** The abstract says all six *published* an analysed extent, but Table 1 lists UNEP as "no extent (stated assumption)" and UH's extent as derived by us from its own footprints, and the reporting-regions table calls the core region an intersection with "all *five* extent-publishing products". Section 1 hedges this correctly ("a defined *or defensible* analysed extent"). Suggest carrying the hedge into the abstract, e.g. "the six for which an analysed extent could be defined or defended".

## ven brief: MS<>CHD (`yaBzQ7Kb`): 3 anchored, 4 detached

- **calebrob6**, 2026-09-04 — detached
  - quote: “xBD building-damage benchmark dataset”
  - note: I'm not quite sure what this means -- the xBD dataset has 4 damage classes

- **calebrob6**, 2026-09-04 — detached
  - quote: “5 Recommendations”
  - note: This section is great

- **calebrob6**, 2026-09-04 — detached
  - quote: “ran from 0.009 (UH) to 0.081 (Microsoft). E”
  - note: This is horrific!

- **calebrob6**, 2026-09-04 — detached
  - quote: “Figure 4: Region: within the CEMS-analysed extents; reference: field reports (20 m GPS tolerance). Recall by damage grade. Each line is one dataset’s recall against field-reported damage, at “complete” destruction versus “significant” damage. Every line slopes down: the products and the expert reference alike find lighter damage far less often, which is why measured recall is an upper bound and measured precision a lower bound.”
  - note: I'd also make this SVG, drop the top and right axis spines, align the x ticks different (they are weirdly crowded to the left). Alternatively would ask claude to directly turn this into an interactive graph

## ven brief: IMPACT<>CHD (`LEbi2d59`): 1 anchored, 1 detached

- **Dimosthenis**, 2026-09-14 — detached
  - quote: “For providers”
  - note: Here and potentially on Table 1, it would be great to add a potential recommendation to publish the spatial resolution of each provided remotely sensed product. Because this is structurally affecting the level of likely damage detection performance and inference, aside from the temporal resolution/dimension and the availability of validation/field data, that you both correctly highlighted. All these three remote sensing components are arguably impacting the precision and accuracy of the discussed damage assessment methods, at different degrees, of course. This is even more prominently amplified due to the fact that the core region area is only 61 sq. km, dictated by the limited assessed AOI by Microsoft, which nevertheless utilized sub-meter state-of-the-art VHR optical satellite images vs 10-m (approx. 400 times more pixels acquired by VHR than Sentinel-1); and the fact that 96% of the CEMS reference damage data is concentrated in the very same core region while some products including ours cover a much broader region i.e. considerably larger delivered extent.

