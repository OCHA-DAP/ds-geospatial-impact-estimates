# Technical brief appendix, rendered snapshot 2026-09-28

Every number resolved, taken from the published render immediately before the trimming
round. Companion to appendix-frozen-2026-09-28.qmd, which holds the source.

## Appendix

<span class="screen-reader-only">Note</span>Show the full appendix

### The two reporting regions

Results are reported in one of two *regions*, and numbers are comparable only within one:

<figure class="quarto-float quarto-float-tbl figure">
<table class="caption-top table" style="width:99%;">
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr class="header">
<th>reporting region</th>
<th>what it is</th>
<th>used for</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td><strong>Core region</strong></td>
<td>the ~61 km² intersection of the CEMS extents with all five extent-publishing products (<a href="#fig-extents" class="quarto-xref">Figure 1</a>): one shared cell set</td>
<td>voting, the pairwise rules, fusion, and the best-F1 geography comparison</td>
</tr>
<tr class="even">
<td><strong>As delivered</strong></td>
<td>each product’s full delivered footprint, wherever CEMS mapped: a different region per product</td>
<td>as-delivered precision and recall, and the geography benchmark; ranking test 1</td>
</tr>
</tbody>
</table>
<figcaption>Table 5: The two reporting regions. Sections and captions state which they use. The core region gives every predictor an identical cell set (one geography score); as-delivered is per-product by design, so the geography model is re-scored on each product’s own footprint there.</figcaption>
</figure>

Why the core region is so small, and what its numbers mean: the five extent-publishing products mutually overlap over only ~100 km², with Microsoft’s 210 km² strip the binding constraint (UNEP publishes no extent and is treated as covering the region, the same stated assumption as everywhere else; UH publishes none either, so its extent is the polygon around its own classified footprints). Intersecting with the expert reference then trims the shared, scoreable area to ~61 km². The trim scores every predictor on the same area, at the cost of representativeness: the core region covers the most heavily damaged area, where the reference is densest and every product scores best, so core-region numbers are each product’s favourable case, while the as-delivered numbers describe what a responder actually had (<a href="#sec-flags" class="quarto-xref">Section 2.1</a>).

Two products that arrived in the same window are not evaluated at all. HOT’s fAIr published no analysed extent, so its misses and false alarms cannot be counted. The same arithmetic is why DISHA is not a member. Its delivery included an analysed extent (133.6 km², north-west Caracas and the La Guaira–Catia strip), but that extent covers only 48% of the core region (29.3 of 60.8 km²) and holds 886 of the 1,467 expert damage points there. Admitting it would have halved the area on which all products are compared and dropped 40% of the reference from every shared analysis, weakening the evaluation of the six other products; it therefore appears in the availability inventory only.

### How complete is the expert reference?

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/reference_architecture.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 7: The three reference datasets at a glance. Two are HOT-run and easily confused: MapSwipe is remote volunteers voting on ~50 m cells, used to adjudicate false alarms; ChatMap is field teams reporting building-level points from the ground, used to reveal misses.</figcaption>
</figure>

The expert reference is itself incomplete, and this was measured rather than assumed. ChatMap, the one reference collected on the ground independently of any satellite imagery, audits the expert map: CEMS captured 94% of field-reported destroyed buildings but only 49% of those significantly damaged (<a href="#fig-gradeslope" class="quarto-xref">Figure 8</a>). The individual products share the same slope: everything sees destruction better than damage. Some damage was missed by everything: about 2% of field-reported damage points inside the area analysed by all of Microsoft, IMPACT, OSU and UH, mostly in inland hill communities, had no flag from any of those four products within 20 m (the same check over all six products is possible only in the core region, where 1% of field reports go unflagged). Recall was never the products’ weakness; precision is the limiting factor.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq2e_grade_slope.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 8: <strong>Region: each product inside its own analysed extent, UNEP and the six-product union inside the core region, the expert map inside its own extent; reference: field reports (20 m GPS tolerance).</strong> Recall by damage grade. Each line is one dataset’s recall against field-reported damage, at “complete” destruction versus “significant” damage; the union line counts a field report as covered if any of the six products flagged a building within 20 m. Every line slopes down: the products and the expert reference alike find lighter damage far less often, which is why measured recall is an upper bound and measured precision a lower bound.</figcaption>
</figure>

### Matching products to references, in full

The product and reference use different geometries (CEMS drops points on damaged buildings, while each product flags its own footprints on its own building base), so there is no shared list of instances on which to build a single confusion matrix. We therefore score by *proximity*, a standard approach for detection-style evaluation: precision anchors on the product (of its flagged buildings, how many have a CEMS damage point within radius r?), and recall anchors on the reference (of the CEMS damage points, how many have a product flag within r?). Each metric has its own denominator. Because the two metrics are precision and recall, neither uses the undamaged background (true negatives), so the size of that set affects no score.

False positives are classified under the standard scheme for detection evaluation. Within the analysed extent the reference is treated as complete: a flag with no reference record within the matching radius is a false positive, reference damage with no flag is a miss, and the remaining buildings are, under the scheme, true negatives (precision and recall never use that count, so it affects no headline number). The rule is applied uniformly, so no product is advantaged by it. What this paper adds is that the completeness assumption is tested rather than assumed: the field reports measure the expert reference’s own recall, every measured precision is reported as a lower bound, and the expert-unmatched flags are re-judged against the crowd (<a href="#sec-flags" class="quarto-xref">Section 2.1</a>).

**From delivered footprints to base buildings.** IMPACT, OSU and LIST reference the shared Overture base directly, so their flags are base buildings as delivered (OSU’s v0 delivery lists 58,870 ids, of which 57,066 are buildings in the evaluation base). Microsoft, UH and UNEP delivered their own footprints, and <a href="#tbl-mapping" class="quarto-xref">Table 6</a> follows those footprints onto the base. Their counts differ from the providers’ for three reasons: two delivered footprints can map to the same base building (UNEP’s finer footprints do so most often), a footprint can reach no base building within 20 m (an orphan), and a footprint can lie outside the frame being scored. The frame columns set the delivered footprints falling in each frame beside the base buildings flagged there, so the denominator of every precision in this brief can be traced back to the delivery.

<figure class="quarto-float quarto-float-tbl figure">
<table class="gt_table cell caption-top table table-sm table-striped small" data-quarto-bootstrap="false">
<thead>
<tr class="gt_col_headings gt_spanner_row header">
<th rowspan="2" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col"></th>
<th colspan="7" id="&lt;strong&gt;Whole-delivery&lt;/strong&gt;" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner"><strong>Whole delivery</strong></span></th>
<th colspan="2" id="&lt;strong&gt;As-delivered&lt;/strong&gt;" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner"><strong>As delivered</strong></span></th>
<th colspan="2" id="&lt;strong&gt;Core-region&lt;/strong&gt;" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner"><strong>Core region</strong></span></th>
</tr>
<tr class="gt_col_headings even">
<th id="delivered" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">delivered footprints</th>
<th id="iou" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">by IoU</th>
<th id="snap" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">nearest ≤ 20 m</th>
<th id="orphans" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">orphans</th>
<th id="base" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">base buildings</th>
<th id="collapsed" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">collapsed</th>
<th id="miou" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">median IoU</th>
<th id="asd_n" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">native</th>
<th id="asd_b" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">base</th>
<th id="core_n" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">native</th>
<th id="core_b" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">base</th>
</tr>
</thead>
<tbody class="gt_table_body">
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">Microsoft</th>
<td class="gt_row gt_right">8,410</td>
<td class="gt_row gt_right">8,410</td>
<td class="gt_row gt_right">0</td>
<td class="gt_row gt_right">0</td>
<td class="gt_row gt_right">8,339</td>
<td class="gt_row gt_right">71</td>
<td class="gt_row gt_right">0.67</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">8,023</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">7,950</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">7,949</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">7,878</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UH</th>
<td class="gt_row gt_right">76,378</td>
<td class="gt_row gt_right">75,329</td>
<td class="gt_row gt_right">1,031</td>
<td class="gt_row gt_right">18</td>
<td class="gt_row gt_right">75,294</td>
<td class="gt_row gt_right">1,066</td>
<td class="gt_row gt_right">0.99</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">57,138</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">56,308</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">5,726</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">5,443</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UNEP</th>
<td class="gt_row gt_right">96,046</td>
<td class="gt_row gt_right">92,820</td>
<td class="gt_row gt_right">3,067</td>
<td class="gt_row gt_right">159</td>
<td class="gt_row gt_right">75,814</td>
<td class="gt_row gt_right">20,073</td>
<td class="gt_row gt_right">0.41</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">23,344</td>
<td class="gt_row gt_right" style="background-color: #e8f0f4">17,937</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">6,887</td>
<td class="gt_row gt_right" style="background-color: #f7e3e1">5,605</td>
</tr>
</tbody>
</table>
<figcaption>Table 6: Own-footprint products mapped onto the shared base by one rule: each delivered footprint goes to the overlapping base building with the highest intersection-over-union, else to the nearest base building within 20 m, else it is an orphan; one assignment per footprint. Collapsed: footprints that share a base building with another footprint. Native: delivered footprints whose location falls in the frame; base: base buildings flagged in the frame (the counts every score uses).</figcaption>
</figure>

<figure class="figure">
<p><img src="figures/rq8c_basis_precision_r10.png" class="figure-img" role="img" width="1216" height="458" /></p>
<figcaption>Dual-anchored matching. Left: a product is scored only where it AND the reference both looked. Middle: recall anchors on the reference; for each CEMS damage point, the question is whether a product flag lies within radius r. Right: precision anchors on the product; for each flagged building, whether a CEMS point lies within r. Each metric has its own denominator.</figcaption>
</figure>

A product is only accountable where both it and the reference actually looked, so all scoring is restricted to the intersection of analysed extents; <a href="#fig-extents" class="quarto-xref">Figure 1</a> maps every extent this paper scores against, and the core region they share. UNEP debris publishes no extent. Based on its density across the study region, we make the explicit assumption that it fully covers the ~61 km² core comparison region, the same logic used for its stand-alone evaluation in fully enclosed administrative units.

An analysed extent shows where a product looked, not whether it could see: cloud can hide individual buildings inside a declared extent. A robustness check against the one product that publishes per-building visibility found the effect negligible in this event ([the cloud check](#app-radius)), so all products are scored without visibility corrections; the check is impossible for the five that publish no such field.

The matching radius comes from an analysis of building spacing rather than from convenience. The median distance between neighbouring building centroids in the core region is 9.6 m, and 93% of buildings have a neighbour within 20 m. We therefore use r = 10 m throughout: with buildings this tightly packed, a larger radius would routinely match a flag to a neighbouring building. The 20 and 30 m columns of <a href="#tbl-dial-full" class="quarto-xref">Table 9</a> serve two purposes at once. Mechanically they are a sensitivity sweep, so the reader can see how every number changes with the buffer. Interpretively, 30 m also works as a *finding distance*: not literal sight of the damage, but close enough that a responder standing at the flag could plausibly find the damaged building. That reading is what makes the 30 m column a visits-per-find workload metric; the sweep is valid without that reading.

Not every CEMS grade counts as damage. CEMS labels each damage point with a text grade. The paper’s reference merges these into two classes: *Destroyed* (destroyed, completely destroyed, or highly damaged; 683 points in the core region) and *Damaged* (moderately damaged or damaged; 784 points). Points graded *possibly damaged* are not in the reference. A flag near one still counts as a false alarm, and a product that misses one loses no recall.

Two analyses relax that choice. In the main text, <a href="#fig-bounds" class="quarto-xref">Figure 2</a> counts the *possibly damaged* points as damage, among other loosenings, to bound each product’s precision from above. Here, <a href="#fig-basis" class="quarto-xref">Figure 9</a> re-scores every predictor of <a href="#fig-bestf1" class="quarto-xref">Figure 5</a> under three definitions of the reference: *Destroyed* only, the paper’s *Damaged or Destroyed*, and also counting *possibly damaged*. Every flag list and operating point is frozen, so only the reference changes.

The grade choice moves levels, not conclusions. Counting *possibly damaged* roughly widens the reference by 1.9× and lifts every precision by 1.1–1.8×, singles and voting rules alike. Recall shifts along the grade slope: grade-neutral products gain, destruction-biased products lose. 5 pairwise comparisons reverse, involving UH, IMPACT, geography null (rand. forest), MS, UNEP. The fused score keeps its ~2.6–3.1× precision margin over the best single product, and the geography null stays inside the product band, under every definition. Excluding *possibly damaged* is the more demanding choice, and we keep it.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq8_dayzero_schematic.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 9: <strong>Region: core (61 km²).</strong> Precision of every <a href="#fig-bestf1" class="quarto-xref">Figure 5</a> predictor under three definitions of the CEMS reference, with flags and operating points frozen, so only the target changes. Grey lines and band: the six products; coloured lines: the composites and the geography nulls. The dashed line marks the paper’s reference. The rise is mechanical (same flags, more reference points to be near); the finding is what does <em>not</em> change: 5 pairwise orderings change (UH, IMPACT, geography null (rand. forest), MS, UNEP).</figcaption>
</figure>

There is one matching rule and two labelled exceptions. Every CEMS-based precision and recall in this paper uses the 10 m radius, so all of them are directly comparable. Two labelled exceptions appear later, each for a different question: the coverage and visits-per-find columns of the voting table use 30 m, the finding distance (“could a responder sent here *find* the damage”), and recall against the ChatMap ground reports uses 20 m. The field exception is not a second convention but the same principle applied to a different reference: the matching radius follows the location precision of the reference being matched. Expert points are digitized onto buildings, so they add no positional error and the 10 m identity radius applies unchanged; field reports are phone points collected from the street (GPS error, and reporters stand near, not on, buildings), so their radius widens to 20 m to allow for the reference’s own positional scatter. Matching those points at 10 m would count the reference’s geolocation error as product failure. Both exceptions are restated where they are used. (That field-matching 20 m is unrelated to the 20 m *label radius* of the Appendix sensitivity re-run, which is an alternative definition of the target itself.)

The radius is not a tolerance applied to the products, but the definition of the target every predictor is scored against:

> A building counts as damaged if a CEMS damage point lies within *r* metres of it.

Widening it changes the target itself, not the leniency of the scoring: at 20 m the identical CEMS points label 3,727 core-region buildings damaged; at 10 m, 2,064. The product-versus-geography comparison is mildly radius-dependent as a result, so every product and voting rule is re-scored at 20 m and 30 m (<a href="#tbl-dial-full" class="quarto-xref">Table 9</a>), the models are refit at both in the Appendix (“Performance versus matching radius”), and no conclusion changes.

“Is a CEMS point within r of this building” is measured one way everywhere in this brief: from the building’s footprint polygon on the shared Overture base. A point on the footprint or within r of its edge is a hit, for single products, voting rules and the fusion labels alike. Products that delivered their own footprints (Microsoft, UNEP, UH) are first mapped onto that base one-to-one by one rule: each delivered footprint goes to the overlapping base building with the highest intersection-over-union, or, if it overlaps none, to the nearest base building within 20 m; the few that reach neither are counted as orphans (<a href="#tbl-mapping" class="quarto-xref">Table 6</a> gives the counts). Gold had used a different rule for each product, and Microsoft’s, any intersecting building, flagged 16% more buildings than it delivered footprints; one rule means no product is credited or penalised for the shape of its own building layer. An earlier draft measured distance from each building’s centre point instead, which under-credits any building whose edge sits within r of a point while its centre does not; in the core region that frame ran 0.02–0.03 lower in precision and 0.12–0.19 lower in recall for every product, and it remains reproducible from the tagged artefacts (`paper-frozen-v3-centroid`; decision record ADR-0030). The radius is the other choice that changes numbers: Microsoft’s precision is 0.122 at 10 m and 0.175 at 20 m, with the same flags scored against the same reference under two definitions of what counts as a hit.

### Area ranking and error structure: method

For questions about where damage is concentrated, we aggregate per-building flags to hexagonal grid cells (H3) at two levels, resolution 8 (~0.74 km²) and resolution 7 (~5.2 km², roughly the size of an operational triage area). We compare each product’s ranking of cells against the ranking implied by CEMS, using rank correlation and top-k overlap.

Whether a ranking survives noisy per-building labels depends on how the noise is arranged in space, so we test that directly. A regression suited to counts (Poisson) predicts each cell’s flag count from its CEMS damage count, with the cell’s building stock built in as the baseline so that “more flags because more buildings” cannot register as bias. What remains (flagging above or below what the real damage explains) is then tested in two ways: for whether it bunches together on the map rather than scattering (Moran’s I, a standard score for exactly this, with its significance judged by reshuffling the values across the same cells many times, which controls for the shape of the built-up area itself), and for correlation with variables that would corrupt a ranking, namely building density, terrain (slope and elevation), and modelled shaking intensity.

Two further tests use the same cell lattice. The first checks whether a product’s reliability in an area can be predicted from its flag pattern alone (its flag rate, how tightly its flags cluster, how much it agrees with the other products), by correlating those signals with measured reliability across every product-and-area combination. The second classifies each product’s territory cell by cell, using local versions of the same clustering score, into places where its errors scatter at random and places where they concentrate.

### Combining products, and adjudicating disagreements: method

For per-building questions, each product’s flags are projected onto the shared Overture footprint base and combined by voting. A building passes the “k-of-6” rule when at least k of the six products flag it. Throughout the paper, k-of-6 refers to a rule, never a score. Voting rules are scored exactly as single products are.

Because CEMS itself has gaps, precision measured against CEMS is a lower bound. A reference gap can turn a correct flag into an apparent false positive, but never the reverse, so the true precision lies at or above the measured value. We estimate how far above by adjudication: for every flagged building with no CEMS point within 10 m, we look up the MapSwipe majority verdict for its cell and count the share that volunteers judged damaged. “Crowd-adjusted precision” adds those confirmed flags back to the numerator. Each precision estimate in this paper is therefore an interval, from the CEMS-measured lower bound to the crowd-adjusted value. One caveat about the upper end: MapSwipe verdicts are per ~50 m cell, not per building (<a href="#fig-refarch" class="quarto-xref">Figure 7</a>), so a crowd-confirmed flag means “damage somewhere in this cell,” not “this building.” The crowd-adjusted value is therefore an *upper* estimate of building-level precision, and the truth lies between it and the CEMS lower bound. The stability of that crowd verdict was itself re-tested: an independent second crowd re-voted the same cells at three times the depth after this paper’s freeze and confirmed 11.1% of the same flags where the first crowd confirmed 12.7%, so the upper estimates here sit slightly high; the mechanism and the full re-test are in the Appendix (<a href="#fig-crowdmech" class="quarto-xref">Figure 14</a>). A second, independent check uses ChatMap instead: because its field points are building-level, they can be unioned directly with the CEMS points, which raises measured precision by a smaller 3–5% (the field data is sparse, 415 points, but geometrically exact).

Recall has no such correction, and its bias runs the other way. Adjudication re-judges flags; it cannot add the damage CEMS never recorded to recall’s denominator: the crowd saw only AI-flagged places, and the field reports are positives-only with no survey frame, so the full denominator is unknowable. Because the reference over-represents destruction, which is the damage class every product detects best, recall measured against it is overstated rather than understated. The rule of thumb for this whole paper: against an incomplete reference, measured precision is a lower bound and measured recall an upper bound. The grade-stratified field-frame measurements in <a href="#sec-flags" class="quarto-xref">Section 2.1</a> quantify how much the recall upper bound overstates.

### The geography benchmark: framing for this brief

Every product was compared against a deliberately simple benchmark that uses no satellite imagery, the *shaking-and-vulnerability null*: modelled shaking intensity from the USGS ShakeMap, and the vulnerability of the setting proxied by building density and by terrain slope and elevation from the open Copernicus 30 m elevation model, fitted with hindsight to this event’s own damage labels and validated on spatial blocks it never trained on. Every input is available on day zero anywhere on Earth; the fitted coefficients were not, so it is a benchmark, not an operational alternative, and it is refit per event rather than carried between them. At building level it falls inside the six products’ performance band (F1 0.159 with the logistic learner, 0.164 with the random forest, against the products’ 0.13–0.19; the logistic is the one reported, so that every paired comparison in this brief rests on one model), and at area ranking it performs comparably to the better single products. Only the combinations exceed it by a wide margin (flat voting +0.16 F1, fitted fusion +0.20). Two checks stand behind it. A covariate ablation (frozen, 2 September) showed that building density alone already comes within 0.01 of the bottom of the six products’ performance band (F1 0.12 against the weakest product’s 0.13), so the benchmark’s strength does not hinge on any one covariate. And because a smooth covariate is where spatial blocks can leak structure across their edges, the model was refit with a 500 m buffer between training and test buildings: the null’s F1 moves from 0.159 to 0.157 and the fusion’s from 0.357 to 0.354, so leakage is not what makes it strong.

The frozen v3 manuscript used a *coast-distance null* (density, distance to the coastline, shaking). Coast distance predicts damage in this event because the damaged strip is a coastal fan, and it is not a variable one would carry to another earthquake; the same ablation showed terrain does the job at least as well (F1 0.18 against 0.17, area-ranking ρ 0.70 against 0.64), so the brief uses the shaking-and-vulnerability null throughout and the conclusions are unchanged (ADR-0033).

### The geography null model and weighted fusion, in full

*How to read this section next to the previous one.* This section is adapted from the frozen v3 manuscript, where the benchmark was reported as a headline result and scored across everything each product delivered; its numbers here are the brief’s shaking-and-vulnerability null, not v3’s coast-distance null. The section above states the brief’s position and scores in the core region. The two agree on the facts and differ in emphasis and in frame: across the delivered footprints the benchmark also carries the shaking estimate, which is why it looks stronger here than in the core-region comparison above.

Two of this paper’s constructions are models rather than products, and both are built the same way. The *geography null model* exists to calibrate what the accuracy numbers mean: it estimates how much of the damage pattern could be recovered from coarse spatial structure and shaking alone, so that a product’s score can be read against something other than zero. It uses four context variables computed per building, all available within hours of any earthquake anywhere: local building density, terrain slope and elevation from the open Copernicus 30 m elevation model, and the shaking intensity estimated by the USGS ShakeMap. From these it predicts which buildings have CEMS-recorded damage. It is validated by *spatial blocking*: the map is cut into ~5.2 km² zones and the model is always scored on zones it was not trained on, because neighbouring buildings resemble each other in both their features and their damage, and an ordinary random split would leak that resemblance into an inflated score (<a href="#fig-dayzero-build" class="quarto-xref">Figure 10</a>).

A null is only meaningful if it is the *strongest* defensible version of “just geography”; a weak one would overstate the products’ skill by construction. We therefore fit it two ways: a logistic regression (a standard statistical model that weighs the three variables) and a random forest (a more flexible model built from many decision trees, able to capture interactions between the variables). Whichever scores higher in a given analysis is the one reported, and both are disclosed. Which of the two wins differs across the paper’s analysis layers; the full comparison and the reasons are in the longer-form draft. Nothing about the fusion results depends on that choice.

We call it a *null model* rather than a baseline, and deliberately avoid naming it after day zero, because the distinction is easy to blur and consequential. Its three inputs are available on day zero; its fitted coefficients are not. Estimating them requires the very damage labels a responder is waiting for, so the model cannot be run on day zero itself. It is not an alternative anyone could have deployed. What it provides instead is a reference level (the standard role of a null model, like a majority-class or stratified-random comparator), and because we allow it to be fitted with hindsight, it is a *generous* null. The two directions therefore read differently. A product that beats it has demonstrated real information beyond spatial structure, and the inference is strong precisely because the null was given every advantage. A product that loses to it has flags placed no better than an obvious retrospective geography prior, which is a serious finding about that product. It is not, however, a claim that geography was an available substitute.

How much *event* information the null actually uses differs by analysis layer: in the core region the shaking estimate barely varies and the model runs on static geography alone, while across the delivered footprints shaking accounts for a quarter to a third of its weight. The as-delivered comparison is consequently the better founded of the two, and the core-region comparison should be read strictly as a null (the detail is in the frozen v3 record, “Was the model-versus-product comparison fair?”, at [pages/manuscript](https://ocha-dap.github.io/ds-geospatial-impact-estimates/manuscript/)).

The model’s output is not a flag list but a continuous risk score per building. Every cutoff on the score is a different flag list, so the model traces a whole curve of precision–recall trade-offs, while a product, whose provider already fixed the threshold, is a single point in that plane; the two are compared point-against-curve. *Average precision*, the area under that curve, is reported only for continuous scores; a shipped product is compared at its operating point instead (the Appendix shows why a one-list “average precision” would mislead).

The *weighted fusion* is the same construction with the six products’ flags and confidence fields added to the three context variables: the geography null is exactly this model with the product inputs removed. Both are refit for each analysis they appear in, always under the same blocked validation. One caution: the learned weights are calibrated to this single event and should not be assumed to transfer.

Two questions of fairness follow from putting a fitted model beside an unfitted product. They are scored on the same data: the validation folds partition the buildings and every building is scored by a model that never saw it, so models and products face identical building sets with identical denominators (the threshold-selection mechanics are in the frozen v3 record, appendix “The geography null model and weighted fusion, in full”). One further hindsight enters through the cut: a product ships one operating point, while each of our scores is reported at the threshold that maximised F1 on the pooled out-of-fold scores, a cut chosen with the labels in view. Re-choosing that cut on the training folds only and applying it blind to each test fold moves the fusion from 0.357 to 0.345 F1, the geography null from 0.159 to 0.129, and flat voting not at all (the best count is 4-of-6 in every fold); the fusion’s margin over counting is 7% under the blind cut against 11% with hindsight. And the model is advantaged by hindsight in a second, deliberate way: it is fitted to this event’s reference labels, so it is an upper bound on geography-only skill for this event, and the claim it supports is about information content (the products add little beyond what three context variables already explain), never the operational claim that responders held such a model on day zero. We return to this in the Limitations.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq3g_frac_vs_count_rho.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 10: How the geography null model is built. Four context variables known within hours of the earthquake (building density, terrain slope and elevation, and ShakeMap intensity) feed one spatially-blocked model whose target is CEMS damage; both learners are fitted and the stronger one is reported (the logistic here, the forest across the larger delivered footprints of <a href="#sec-flags" class="quarto-xref">Section 2.1</a>). Its output is a <em>continuous</em> per-building risk, so every threshold on it is a different flag list and the score traces an entire precision–recall curve, against which a single product is one already-thresholded point. No satellite product enters this model. Note what the diagram cannot show: fitting it requires the damage labels themselves, which is why it is a retrospective null rather than something available on the day its inputs are.</figcaption>
</figure>

### Area-ranking detail: tables and error structure

Because area ranking is the products’ strongest result, we run the same null test on it as on the building-level numbers (the first of this paper’s three product-versus-geography comparisons; the v3 record’s null-comparison table lists all three). We summed the geography model’s predicted per-building risk (each building’s risk always taken from a model fit that had never seen its neighbourhood) over exactly the cells used above, giving an expected damage count per cell that needs no threshold, and correlated those with the CEMS count the same way:

<figure class="quarto-float quarto-float-tbl figure">
<table class="cell caption-top table table-sm table-striped small">
<thead>
<tr class="header">
<th>scale</th>
<th>product</th>
<th>ρ product</th>
<th>ρ geography null</th>
<th>difference</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>~5 km² (res 7)</td>
<td>Microsoft</td>
<td>0.602</td>
<td><strong>0.778</strong></td>
<td>−0.175</td>
</tr>
<tr class="even">
<td>~5 km² (res 7)</td>
<td>IMPACT v2</td>
<td>0.433</td>
<td><strong>0.665</strong></td>
<td>−0.232</td>
</tr>
<tr class="odd">
<td>~5 km² (res 7)</td>
<td>OSU</td>
<td>0.540</td>
<td><strong>0.560</strong></td>
<td>−0.020</td>
</tr>
<tr class="even">
<td>~5 km² (res 7)</td>
<td>UH</td>
<td>-0.073</td>
<td><strong>0.695</strong></td>
<td>−0.768</td>
</tr>
<tr class="odd">
<td>~5 km² (res 7)</td>
<td>LIST</td>
<td>0.404</td>
<td><strong>0.552</strong></td>
<td>−0.147</td>
</tr>
<tr class="even">
<td>~5 km² (res 7)</td>
<td>UNEP</td>
<td>0.222</td>
<td><strong>0.573</strong></td>
<td>−0.351</td>
</tr>
<tr class="odd">
<td>~0.7 km² (res 8)</td>
<td>Microsoft</td>
<td>0.474</td>
<td><strong>0.599</strong></td>
<td>−0.125</td>
</tr>
<tr class="even">
<td>~0.7 km² (res 8)</td>
<td>IMPACT v2</td>
<td>0.292</td>
<td><strong>0.573</strong></td>
<td>−0.281</td>
</tr>
<tr class="odd">
<td>~0.7 km² (res 8)</td>
<td>OSU</td>
<td>0.505</td>
<td><strong>0.515</strong></td>
<td>−0.010</td>
</tr>
<tr class="even">
<td>~0.7 km² (res 8)</td>
<td>UH</td>
<td>-0.114</td>
<td><strong>0.567</strong></td>
<td>−0.681</td>
</tr>
<tr class="odd">
<td>~0.7 km² (res 8)</td>
<td>LIST</td>
<td>0.276</td>
<td><strong>0.461</strong></td>
<td>−0.185</td>
</tr>
<tr class="even">
<td>~0.7 km² (res 8)</td>
<td>UNEP</td>
<td>0.071</td>
<td><strong>0.489</strong></td>
<td>−0.418</td>
</tr>
</tbody>
</table>
<figcaption>Table 7: How well each ranking matches the expert damage count per cell (rank correlation, Spearman’s ρ): each product against the geography model, on identical cells within that product’s shared region. The two scales are H3 resolution 7 and resolution 8 hexagons (sizes in the text). The larger of the two correlations in each row is in bold.</figcaption>
</figure>

Across the delivered footprints, geography alone ranks these areas better than the products do, beating six of the six at the ~5.2 km² scale and six of six at the finer scale. The margins are large (IMPACT 0.665 against 0.433, UNEP 0.573 against 0.222), and a negative rank correlation for UH (−0.073) means an ordering of the ~5.2 km² cells slightly worse than no information at all. Only none is ahead of the null at the ~5.2 km² scale, and only narrowly (0.540 against 0.560).

That comparison spans all five mapped areas, however, and 96% of the reference damage sits in one of them. Much of what it rewards is therefore the coarse discrimination of Caraballeda from four quiet AOIs, a task building density and terrain solve almost by definition (the damaged strip is the dense, low-lying coastal fan). The sharper question is whether the products can out-rank geography *within* the damage zone, and there the result is different. Re-running the test in the core region, the brief’s within-damage-zone frame, at resolution 8 cells, three of the six beat the null (<a href="#tbl-nullrank-core" class="quarto-xref">Table 8</a>): IMPACT v2, OSU, LIST; Microsoft, UH, UNEP fall below it; and at resolution 9 (~0.1 km²) two of six are ahead. So the products do contain real information about where within a damaged area to go first: what they do not add is knowledge of which area that is, which is the part geography already encodes. The headline five-of-six should be read as a statement about the coarse task, not as evidence that the products are uninformative at every scale.

<figure class="quarto-float quarto-float-tbl figure">
<table class="cell caption-top table table-sm table-striped small">
<thead>
<tr class="header">
<th>product</th>
<th>ρ product</th>
<th>ρ geography null</th>
<th>difference</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>LIST</td>
<td><strong>0.737</strong></td>
<td>0.680</td>
<td>+0.057</td>
</tr>
<tr class="even">
<td>IMPACT v2</td>
<td><strong>0.718</strong></td>
<td>0.680</td>
<td>+0.038</td>
</tr>
<tr class="odd">
<td>OSU</td>
<td><strong>0.703</strong></td>
<td>0.680</td>
<td>+0.023</td>
</tr>
<tr class="even">
<td>Microsoft</td>
<td>0.616</td>
<td><strong>0.680</strong></td>
<td>−0.064</td>
</tr>
<tr class="odd">
<td>UNEP</td>
<td>0.579</td>
<td><strong>0.680</strong></td>
<td>−0.102</td>
</tr>
<tr class="even">
<td>UH</td>
<td>0.477</td>
<td><strong>0.680</strong></td>
<td>−0.203</td>
</tr>
</tbody>
</table>
<figcaption>Table 8: The same test in the core region, resolution 8 cells, sorted by the product’s margin over the geography null. The larger of the two correlations in each row is in bold.</figcaption>
</figure>

The caveat stated earlier applies to this interpretation: the null is hindsight-fitted (the [geography benchmark](#app-null-brief)), so this says the damage pattern was largely recoverable from geography *after the fact*, not that a responder had this ranking on day one. What it does rule out is the reading that area ranking demonstrates the products are extracting damage information the geography does not already contain. At this scale they are reproducing a spatial pattern, competently, that was largely predictable from the map.

A natural objection is that ranking by damage *count* favours geography by construction: counts partly rank building stock, so dense urban cells rise regardless of how hard they were hit, and a model fed building density inherits that for free. Re-ranking by damage *fraction* (damaged buildings divided by the cell’s building stock, on cells with at least 20 buildings) tests exactly that, and the objection fails (<a href="#fig-fracrank" class="quarto-xref">Figure 11</a>). The null ranks fractions about as well as it ranks counts (ρ 0.45–0.60): damage *rate* is itself geographically structured in this event, high near the coast and low inland, so dividing out the stock removes nothing the null relies on. No conclusion changes: the products ahead of the null at ~0.74 km² are OSU by count and OSU by fraction. The products themselves split as their grade bias predicts: the two Sentinel-1 products gain under fractions (IMPACT 0.29 to 0.47 at ~0.74 km²) while the appearance-based products lose (Microsoft 0.47 to 0.36, UH -0.11 to -0.21). Count remains the headline target because the triage question is where the most damaged buildings are; the fraction view answers severity, and both give the same verdict on the products.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq3_residual_maps_res8.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 11: <strong>Region: as delivered; both cell scales.</strong> Each product’s rank correlation with the expert ordering when cells are ranked by damaged-building count (filled circles, the paper’s target) versus damage fraction (filled squares; cells with at least 20 buildings). Open markers: the geography null under each target. The null is as strong under fractions as under counts, and only OSU beats it under either.</figcaption>
</figure>

The error-structure test explains why area ranking works despite the per-building noise. The residual over-flagging is strongly clustered in space (Moran’s I 0.26–0.54, p ≤ 0.001 for each of the three products this test covers: Microsoft, IMPACT, and OSU, the members whose extents overlap CEMS broadly enough for the cell-level regression; extending it to the newer members is open work), so the errors are not random noise. But once building stock is controlled, the clustering follows the earthquake itself: residuals rise toward the coast and with modelled shaking, and show no association with building density. The specific worry that flags merely reproduce the building map finds no support once building stock is controlled. In short, the products over-call most where damage is worst. That error structure preserves area rankings. The dangerous alternative, errors that track urban form, is what the test rules out.

<figure class="figure">
<p><img src="figures/rq2i_per_aoi_scorecard.png" class="img-fluid figure-img" role="img" /></p>
<figcaption>Where each product over-flags once its building stock is accounted for (red = more flags than the recorded damage explains), for the three products the error-structure test covers. Each panel autoscales to its own analysed region, which is why they look so different: Microsoft analysed a single ~30 km coastal strip, so its few hundred grid cells appear as individual dots, while IMPACT and OSU are Sentinel-1 swaths spanning roughly 200 km, whose thousands of cells merge visually. IMPACT and OSU residuals follow the coastal severity gradient. Microsoft’s error is a single hard cluster at the west end of its region.</figcaption>
</figure>

The same cell lattice yields one further result. Mapping each product’s errors cell by cell, 84%–87% of each product’s territory shows errors scattered at random (noise rather than bias), with the failures concentrated in a few identifiable pockets; Microsoft’s western strip, taken up in the [west-strip case study](#app-weststrip), is the largest.

One product does not fit this benign pattern. Microsoft’s residual error is not a gradient but a single dense cluster in the western coastal strip, and no covariate explains it. At this point in the analysis we cannot say what the cluster is: real over-detection and a local gap in the reference would look identical. The [west-strip case study](#app-weststrip) resolves the question with the other two references.

That ambiguity applies to every number in this section, not just the anomaly. Everything above assumes CEMS is complete within its extents. The next section tests that assumption.

### Precision and recall in both frames, in full

The pooled numbers are one place’s numbers. That fact bounds every headline number in this paper. CEMS activated five separate AOIs, but 96% of its damage points sit in one of them: Caraballeda (1,468 points, against 26 in Morón, 14 in San Felipe, and 3 each in Caracas and Santa Cruz). Splitting the results by AOI (<a href="#fig-peraoi" class="quarto-xref">Figure 12</a>) shows two things. First, the pooled numbers *are* Caraballeda’s numbers: the Caraballeda row reproduces the baseline precision and recall almost exactly. Second, outside Caraballeda every product keeps flagging at scale (IMPACT marks 9,444 buildings in the Caracas AOI, UH marks 32,144, 27.5% of the stock, in Santa Cruz) while measured precision collapses to 0.00–0.02 everywhere. Those zeros are lower bounds against a reference that recorded almost nothing in those AOIs, so two explanations are confounded: the products over-flagging at scale where damage is sparse (the same low-damage-zone mechanism as the UH agricultural case and the Microsoft west strip), and CEMS under-recording damage in AOIs it mapped thinly. The crowd cannot arbitrate here: the MapSwipe campaign concentrated on the coastal strip, and at most 12% of these out-of-Caraballeda flags fall on MapSwipe-voted cells. Recall is measurable only in Morón (26 points), where the best product finds 23% of it. What remains after the ambiguity is a statement of scope: every performance claim in this paper describes dense-damage coastal terrain, and in the four low-damage AOIs the products’ flags are almost entirely uncorroborated by any reference we have.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq7_west_cluster_adjudication.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 12: <strong>Region: each CEMS AOI separately, plus the pooled as-delivered total.</strong> Precision and recall by AOI. Left: baseline precision per product per CEMS AOI; right: recall. 96% of all CEMS damage points are in Caraballeda; outside it, measured precision (0.00–0.02) cannot separate product over-flagging from reference incompleteness.</figcaption>
</figure>

Pooling all five AOIs gives the *as-delivered* numbers: the product as a responder received it, low-damage zones included. As-delivered precision: Microsoft 0.121, OSU 0.054, IMPACT 0.048, LIST 0.040, UNEP 0.037, UH 0.012. One assumption is doing more work here than in the core region: UNEP published no analysed extent, so in this frame it is scored as if it had examined all five expert-mapped areas, Caracas and the inland towns included. Where UNEP has no flags there, that may mean “never looked” rather than “saw nothing”, so its as-delivered precision and recall are the values under that stated assumption, not measurements of a delivery whose scope we know. UH’s number is ten times worse than its best-case 0.124, because most of its flags sit in the low-damage AOIs (32,144 in Santa Cruz alone). And Microsoft’s number is *unchanged*, because it published flags only for the coastal strip it had analysed carefully. Restraint in coverage is itself a product property: shipping fewer, better-scoped zones protected Microsoft’s as-delivered precision, while shipping everywhere sharply lowered UH’s.

Two mechanisms explain the as-delivered numbers, and they answer the obvious objection: *shouldn’t precision fall sharply outside the one dense zone?* The first is arithmetic. Because almost no damage was recorded in the four low-damage AOIs, precision there is essentially zero, and the pooled figure is a flag-weighted average, so a product’s as-delivered precision falls by almost exactly the share of its flags that land outside Caraballeda: Microsoft 0% of flags and 0% lost, OSU 17% and 17%, IMPACT 52% and 52%, LIST 52% and 51%, UNEP 68% and 68%, UH 90% and 90% (every product falls on the diagonal *precision lost = share of flags in the low-damage AOIs*; plotted in the longer-form draft). Precision collapses in direct proportion to where each product chose to flag. Second, even this understates the problem: the as-delivered frame can only score flags that fall inside a CEMS extent, and most products flag far beyond one. Of each product’s total flags, the share landing outside every CEMS extent (where no reference can score them at all) is 5% for Microsoft but 43% for OSU, 71% for IMPACT, 76% for UNEP, and 79% for LIST. Since damage was concentrated on the coast, the bulk of those unscoreable flags are almost certainly false positives. So every precision figure in this paper, as-delivered included, is measured on each product’s most favourable, reference-covered subset; the true precision across a product’s full output is very likely lower, and unmeasurably so.

We also re-ran this paper’s harshest benchmark in the as-delivered frame (the second of the three product-versus-geography comparisons of the null-comparison table in the v3 record). We trained the geography null model (building density, terrain slope and elevation, and ShakeMap intensity, constructed as described in the [geography benchmark](#app-null-brief)) on each product’s full delivered footprint under the same spatially blocked validation, then had it flag exactly as many buildings as that product shipped, taking its highest-risk buildings first. Compared this way, list against list at each product’s own delivered size, four of the six products are beaten by the geography model on precision (pairs below read precision / recall): IMPACT 0.048 / 0.54 against the model’s 0.063 / 0.70; UH 0.012 / 0.33 against 0.035 / 0.95; LIST 0.040 / 0.64 against 0.043 / 0.70; and UNEP 0.037 / 0.31 against 0.062 / 0.52. At UH’s own list size the geography rule reaches 95% of the reference damage at 2.9 times UH’s precision. Microsoft (0.121 / 0.47 against 0.100 / 0.38), which shipped only its carefully analysed strip, and OSU (0.054 / 0.84 against 0.051 / 0.79), which flagged so widely it reached recall the null could not match at that list length, are the products the comparison favours. This result is unchanged by the matching radius: repeated at 20 m it is the same four products, in the same direction (Appendix). One caveat applies to all of this: outside Caraballeda the reference is thin, and the penalty for flagging there falls on the products, which did flag, not on the baseline, which did not. To whatever extent CEMS under-recorded those areas, part of the gap would close. But a responder in the first week had exactly the same information deficit, which is the point of the as-delivered frame.

### The single-product ceiling: three experiments

Three independent experiments in this event indicate that a better single product would not fix per-building precision. The limit looks like a property of the sensing method rather than of any particular product. We refer to it as the modality ceiling: a precision level that single-method tuning does not rise above. (Note that this is the opposite kind of bound from the reference-driven lower bounds of <a href="#sec-flags" class="quarto-xref">Section 2.1</a>: those mean the truth is higher than measured; the ceiling means single-product performance stops improving.)

1.  Same-satellite agreement barely helps. Requiring the two Sentinel-1 products (IMPACT, amplitude change; OSU, coherence change) to agree raises precision only to 0.132, barely above the single products, the weakest of the fifteen pairs. They share a satellite but not a signal, and this event does not say which of the two is why their agreement adds so little.
2.  Product confidence scores add nothing. Sweeping Microsoft’s continuous damage-fraction score (within its own analysed region, where its baseline numbers run higher than in the core region) trades recall 0.66→0.10 for precision 0.09→0.17. The shipped binary flag already sits near the best F1 on that curve. No additional precision is available from the confidence field. OSU’s post-freeze v1 certainty tiers repeat the pattern ([version postscript](#app-osu-v1)).
3.  Agreement within one product plateaus too. Microsoft flags corroborated by a second satellite scene are 2.5 times more precise than single-scene flags (0.245 versus 0.097, scored on Microsoft’s own scene footprints by centroid distance; this experiment’s per-scene inputs were not archived, so it was not re-run in the footprint frame and the ratio is the durable result). That is a real gain and worth publishing. But it remains well below the strongest two-product rule (0.557), and in the low-damage zone where two scenes overlap, even flags confirmed by both scenes were rejected by 72% of crowd reviews. Agreement inside one model inherits that model’s calibration failures.

### The west-strip case study, in full

The Microsoft west-strip anomaly was left unexplained above. It can now be resolved completely, and the resolution is the paper’s best argument for metadata transparency.

The crowd settles what the cluster is, and it has to be the crowd: this strip is where the expert map records far less than the products flag, and a thin reference cannot separate over-flagging from its own incompleteness, whereas the crowd reviewed exactly the flagged cells. In the western strip, volunteers judged 71% of Microsoft-flagged locations “no damage”, against a roughly even split in the damage-dense east. Independent people looking at post-event imagery saw nothing at most of the places the cluster flags (<a href="#fig-weststrip" class="quarto-xref">Figure 13</a>). The cluster is real over-detection, not a gap in the reference.

<figure class="quarto-float quarto-float-fig figure">
<img src="figures/rq7_crowd_adjustment_explainer.png" class="img-fluid figure-img" role="img" />
<figcaption>Figure 13: <strong>Region: the western half of Microsoft’s delivered strip (Catia La Mar).</strong> Top left: where Microsoft flags far more than the expert map records. Bottom left: where crowd volunteers said nothing is there. Right: cell by cell the two do not track; the agreement is at the scale of the strip, which sat under a single satellite scene.</figcaption>
</figure>

The product’s own metadata explains where it came from. Every building in the strip has `num_observations = 1`: the zone was covered by exactly one satellite scene, processed alone. Microsoft’s own public report identifies this area (the Catia La Mar overlap) as its largest source of disagreement between scenes: its 25 June Vantor scene flagged ~2,600 buildings as damaged that its 26 June Planet scene calls intact, and where both scenes existed the merge kept the later Planet read; the failing strip is where there was no second scene to overrule the first. The platform behind the product (HASTE; Robinson, Ortiz et al. 2026) trains a fresh model for each scene and uses agreement between overlapping scenes as its only internal check. The west never got that check. Cloud is ruled out as an alternative explanation: the west is the most cloud-free zone in the product, and the [visibility check](#app-radius) changed nothing. Splitting the product at the scene boundary shows what was hidden inside the headline number. The single-scene west flags 28.7% of its buildings, with precision 0.05. The multi-scene east flags 8.2%, with precision 0.20, the best single-product zone we measured anywhere in this study. The same product contains both.

A head-to-head test of the two overlapping scenes identifies the mechanism. Scored independently on the ~24,700 buildings both scenes covered, the “better” scene’s advantage turns out to be restraint, not accuracy: it flags 4.9% of buildings against the other’s 27.8%, but its flags are crowd-confirmed at a lower rate (7% versus 14%). Microsoft’s merge rule, which resolved conflicts in favour of that scene, was directionally right (68% of the overruled flags were crowd-rejected) but in doing so discarded roughly 845 flags on buildings the crowd judged damaged. And buildings flagged by both scenes were still 72% crowd-rejected in this low-damage zone. The failure unit is the calibration of each per-scene model, not the satellite, the provider, or the product as a whole.

A cross-product control confirms that attribution. UH’s authors confirm their analysis ran exclusively on Vantor imagery (the same commercial source as the failing scene) and over the same strip UH shows the opposite pattern: it flags 3.4% of buildings in the west at precision 0.186 (its best zone anywhere), against Microsoft’s 28.7% at 0.052. With the same imagery vendor but a different model, the cluster does not appear, so the failure lies in the per-scene calibration rather than the pixels. (UH’s acquisition dates are unconfirmed, so this is vendor-level rather than scene-level evidence.)

Much of this case study generalizes. A single product-level metric averaged over a 4× internal quality split, and the split was only detectable because per-building provenance was published. The failure was not predictable from the provider’s own validation: by the per-scene precision figures in their published report, the affected scene was exactly the one absent from their labeled validation set, and the platform’s previous external evaluation (Turkey) showed the opposite bias, conservative under-flagging; per-scene behaviour in a new event was not predictable from the track record. And the diagnosis was available during the response: the crowd campaign that rejected 71% of the strip’s flags finished within days of the flags being published, but there was no mechanism for returning that finding to the provider. For the five products that publish no per-building provenance, we can see where they err, but never why.

### A version postscript: what a product revision changes

One provider revised its product after the study window: OSU delivered a v1 on 22 July (confidence tiers, expanded coverage, 69,431 flags versus v0’s 58,870). We score v0 throughout, because v0 is what responders had during the response; the operational dashboard now uses v1. Since both versions are built on the same building base, they can be scored identically on the common extent against the same 1,488 CEMS points (this comparison spans OSU’s full extent, so its precision runs lower than its core-region value). The result: precision 0.054 (v0) versus 0.051 (v1), recall 0.86 versus 0.81, minimal accuracy change, while more than half the flag list turned over (v1 dropped 30,565 of v0’s 57,066 flags and added 42,723 new ones). A revision that relabels half the buildings without moving precision or recall is itself evidence for this paper’s central reading: at the individual-building level these products are noise-dominated, and such products should be judged on version-to-version stability as well as accuracy. The area-level signal, by contrast, is robust to exactly this kind of churn.

The revision’s other addition, the certainty tiers, lets us ask a question v0 could not: does a product’s *most confident* class rise above the per-building ceiling? (v0’s continuous score was too saturated for this question: 51% of its flags sat at probability exactly 1.0.) Scored in the core region, the frame of <a href="#tbl-dial" class="quarto-xref">Table 4</a>, the tiers are correctly ordered and the high-confidence cut is v1’s best operating point: precision 0.087, against 0.052 for the probable tier and 0.070 for the published headline, with F1 0.151 versus the headline’s 0.129 (recall 0.57 against 0.82). So the tiering is a real quality signal, and it still does not change the conclusion: OSU’s best tier remains below Microsoft’s core-region precision (0.122) and far below the agreement rules, so the [ceiling appendix’s](#app-ceiling) confidence finding, real signal but no additional precision to gain from thresholding it, now rests on two products rather than one.

### Performance versus matching radius

<figure class="quarto-float quarto-float-tbl figure">
<table class="gt_table cell caption-top table table-sm table-striped small" style="width:98%;" data-quarto-bootstrap="false">
<colgroup>
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
<col style="width: 7%" />
</colgroup>
<thead>
<tr class="gt_col_headings gt_spanner_row header">
<th rowspan="2" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col"></th>
<th rowspan="2" id="flags" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">flags</th>
<th colspan="5" id="10-m" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner">10 m</span></th>
<th colspan="3" id="20-m" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner">20 m</span></th>
<th colspan="4" id="30-m" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner">30 m</span></th>
</tr>
<tr class="gt_col_headings even">
<th id="P10" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">P</th>
<th id="R10" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">R</th>
<th id="F110" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">F1</th>
<th id="Padj" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">P<br />
(crowd-adj)</th>
<th id="cov" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">crowd<br />
reviewed</th>
<th id="P20" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">P</th>
<th id="R20" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">R</th>
<th id="F120" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">F1</th>
<th id="P30" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">P</th>
<th id="R30" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">R</th>
<th id="F130" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">F1</th>
<th id="visits" class="gt_col_heading gt_columns_bottom_border gt_right" data-quarto-table-cell-role="th" scope="col">visits<br />
per find</th>
</tr>
</thead>
<tbody class="gt_table_body">
<tr class="gt_group_heading_row odd">
<th colspan="14" class="gt_group_heading" data-quarto-table-cell-role="th">Products</th>
</tr>

<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">Microsoft</td>
<td class="gt_row gt_right">7,878</td>
<td class="gt_row gt_right" style="background-color: #d0e1f2">0.122 (0.121)</td>
<td class="gt_row gt_right" style="background-color: #79b5d9">0.611 (0.611)</td>
<td class="gt_row gt_right" style="background-color: #a8cee4">0.203</td>
<td class="gt_row gt_right" style="background-color: #c7dcef">0.270</td>
<td class="gt_row gt_right">99%</td>
<td class="gt_row gt_right" style="background-color: #d0e1f2">0.175</td>
<td class="gt_row gt_right" style="background-color: #69add5">0.703</td>
<td class="gt_row gt_right" style="background-color: #a9cfe5">0.281</td>
<td class="gt_row gt_right" style="background-color: #cfe1f2">0.218</td>
<td class="gt_row gt_right" style="background-color: #5ba3d0">0.774</td>
<td class="gt_row gt_right" style="background-color: #afd1e7">0.340</td>
<td class="gt_row gt_right" style="background-color: #56a0ce">6.9</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">IMPACT v2</td>
<td class="gt_row gt_right">10,787</td>
<td class="gt_row gt_right" style="background-color: #d2e3f3">0.104 (0.048)</td>
<td class="gt_row gt_right" style="background-color: #74b3d8">0.627 (0.619)</td>
<td class="gt_row gt_right" style="background-color: #b7d4ea">0.178</td>
<td class="gt_row gt_right" style="background-color: #d2e3f3">0.187</td>
<td class="gt_row gt_right">48%</td>
<td class="gt_row gt_right" style="background-color: #cfe1f2">0.179</td>
<td class="gt_row gt_right" style="background-color: #69add5">0.702</td>
<td class="gt_row gt_right" style="background-color: #a6cee4">0.285</td>
<td class="gt_row gt_right" style="background-color: #cbdef1">0.252</td>
<td class="gt_row gt_right" style="background-color: #5ca4d0">0.770</td>
<td class="gt_row gt_right" style="background-color: #99c7e0">0.379</td>
<td class="gt_row gt_right" style="background-color: #69add5">9.5</td>
</tr>
<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">OSU</td>
<td class="gt_row gt_right">25,882</td>
<td class="gt_row gt_right" style="background-color: #d7e6f5">0.068 (0.054)</td>
<td class="gt_row gt_right" style="background-color: #3e8ec4">0.865 (0.856)</td>
<td class="gt_row gt_right" style="background-color: #d0e1f2">0.126</td>
<td class="gt_row gt_right" style="background-color: #d7e6f5">0.144</td>
<td class="gt_row gt_right">43%</td>
<td class="gt_row gt_right" style="background-color: #d6e6f4">0.118</td>
<td class="gt_row gt_right" style="background-color: #3a8ac2">0.914</td>
<td class="gt_row gt_right" style="background-color: #cddff1">0.209</td>
<td class="gt_row gt_right" style="background-color: #d5e5f4">0.170</td>
<td class="gt_row gt_right" style="background-color: #3888c1">0.935</td>
<td class="gt_row gt_right" style="background-color: #caddf0">0.288</td>
<td class="gt_row gt_right" style="background-color: #b5d4e9">18.9</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UH</td>
<td class="gt_row gt_right">5,443</td>
<td class="gt_row gt_right" style="background-color: #d0e1f2">0.124 (0.012)</td>
<td class="gt_row gt_right" style="background-color: #a4cce3">0.453 (0.451)</td>
<td class="gt_row gt_right" style="background-color: #add0e6">0.195</td>
<td class="gt_row gt_right" style="background-color: #d0e2f2">0.201</td>
<td class="gt_row gt_right">26%</td>
<td class="gt_row gt_right" style="background-color: #cfe1f2">0.180</td>
<td class="gt_row gt_right" style="background-color: #a0cbe2">0.502</td>
<td class="gt_row gt_right" style="background-color: #b2d2e8">0.265</td>
<td class="gt_row gt_right" style="background-color: #cfe1f2">0.222</td>
<td class="gt_row gt_right" style="background-color: #95c5df">0.563</td>
<td class="gt_row gt_right" style="background-color: #bad6eb">0.319</td>
<td class="gt_row gt_right" style="background-color: #549fcd">6.6</td>
</tr>
<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">LIST</td>
<td class="gt_row gt_right">15,906</td>
<td class="gt_row gt_right" style="background-color: #d5e5f4">0.086 (0.040)</td>
<td class="gt_row gt_right" style="background-color: #56a0ce">0.755 (0.734)</td>
<td class="gt_row gt_right" style="background-color: #c6dbef">0.154</td>
<td class="gt_row gt_right" style="background-color: #d5e5f4">0.164</td>
<td class="gt_row gt_right">45%</td>
<td class="gt_row gt_right" style="background-color: #d3e3f3">0.149</td>
<td class="gt_row gt_right" style="background-color: #4493c7">0.864</td>
<td class="gt_row gt_right" style="background-color: #b7d4ea">0.255</td>
<td class="gt_row gt_right" style="background-color: #d0e2f2">0.211</td>
<td class="gt_row gt_right" style="background-color: #3c8cc3">0.909</td>
<td class="gt_row gt_right" style="background-color: #aed1e7">0.342</td>
<td class="gt_row gt_right" style="background-color: #7db8da">11.9</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UNEP</td>
<td class="gt_row gt_right">5,605</td>
<td class="gt_row gt_right" style="background-color: #d0e2f2">0.117 (0.037)</td>
<td class="gt_row gt_right" style="background-color: #a9cfe5">0.431 (0.421)</td>
<td class="gt_row gt_right" style="background-color: #b3d3e8">0.184</td>
<td class="gt_row gt_right" style="background-color: #caddf0">0.253</td>
<td class="gt_row gt_right">88%</td>
<td class="gt_row gt_right" style="background-color: #d0e1f2">0.171</td>
<td class="gt_row gt_right" style="background-color: #97c6df">0.541</td>
<td class="gt_row gt_right" style="background-color: #b5d4e9">0.259</td>
<td class="gt_row gt_right" style="background-color: #d0e2f2">0.211</td>
<td class="gt_row gt_right" style="background-color: #81badb">0.633</td>
<td class="gt_row gt_right" style="background-color: #bdd7ec">0.316</td>
<td class="gt_row gt_right" style="background-color: #4f9bcb">6.0</td>
</tr>
<tr class="gt_group_heading_row even">
<td colspan="14" class="gt_group_heading" data-quarto-table-cell-role="th">Voting rules (k of 6 agree)</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">1-of-6</td>
<td class="gt_row gt_right">37,346</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.053</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.952</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.100</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.128</td>
<td class="gt_row gt_right">45%</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.094</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.982</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.171</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.136</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.986</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.239</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">25.8</td>
</tr>
<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">2-of-6</td>
<td class="gt_row gt_right">20,766</td>
<td class="gt_row gt_right" style="background-color: #d5e5f4">0.085</td>
<td class="gt_row gt_right" style="background-color: #3888c1">0.899</td>
<td class="gt_row gt_right" style="background-color: #c4daee">0.155</td>
<td class="gt_row gt_right" style="background-color: #d3e3f3">0.179</td>
<td class="gt_row gt_right">55%</td>
<td class="gt_row gt_right" style="background-color: #d3e3f3">0.147</td>
<td class="gt_row gt_right" style="background-color: #3484bf">0.948</td>
<td class="gt_row gt_right" style="background-color: #b8d5ea">0.254</td>
<td class="gt_row gt_right" style="background-color: #d0e2f2">0.207</td>
<td class="gt_row gt_right" style="background-color: #3282be">0.964</td>
<td class="gt_row gt_right" style="background-color: #afd1e7">0.341</td>
<td class="gt_row gt_right" style="background-color: #97c6df">14.7</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">3-of-6</td>
<td class="gt_row gt_right">9,140</td>
<td class="gt_row gt_right" style="background-color: #ccdff1">0.148</td>
<td class="gt_row gt_right" style="background-color: #4f9bcb">0.781</td>
<td class="gt_row gt_right" style="background-color: #85bcdc">0.250</td>
<td class="gt_row gt_right" style="background-color: #c8dcf0">0.262</td>
<td class="gt_row gt_right">67%</td>
<td class="gt_row gt_right" style="background-color: #c7dcef">0.239</td>
<td class="gt_row gt_right" style="background-color: #4695c8">0.856</td>
<td class="gt_row gt_right" style="background-color: #69add5">0.374</td>
<td class="gt_row gt_right" style="background-color: #bfd8ed">0.322</td>
<td class="gt_row gt_right" style="background-color: #4090c5">0.890</td>
<td class="gt_row gt_right" style="background-color: #5ca4d0">0.472</td>
<td class="gt_row gt_right" style="background-color: #57a0ce">7.0</td>
</tr>
<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">4-of-6</td>
<td class="gt_row gt_right">3,123</td>
<td class="gt_row gt_right" style="background-color: #b3d3e8">0.268</td>
<td class="gt_row gt_right" style="background-color: #85bcdc">0.566</td>
<td class="gt_row gt_right" style="background-color: #3a8ac2">0.364</td>
<td class="gt_row gt_right" style="background-color: #a9cfe5">0.416</td>
<td class="gt_row gt_right">87%</td>
<td class="gt_row gt_right" style="background-color: #aacfe5">0.385</td>
<td class="gt_row gt_right" style="background-color: #77b5d9">0.653</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.484</td>
<td class="gt_row gt_right" style="background-color: #a3cce3">0.461</td>
<td class="gt_row gt_right" style="background-color: #69add5">0.718</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.562</td>
<td class="gt_row gt_right" style="background-color: #3b8bc2">3.0</td>
</tr>
<tr class="odd">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">5-of-6</td>
<td class="gt_row gt_right">915</td>
<td class="gt_row gt_right" style="background-color: #7ab6d9">0.474</td>
<td class="gt_row gt_right" style="background-color: #bfd8ed">0.329</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.388</td>
<td class="gt_row gt_right" style="background-color: #6fb0d7">0.636</td>
<td class="gt_row gt_right">97%</td>
<td class="gt_row gt_right" style="background-color: #71b1d7">0.612</td>
<td class="gt_row gt_right" style="background-color: #b8d5ea">0.397</td>
<td class="gt_row gt_right" style="background-color: #3080bd">0.481</td>
<td class="gt_row gt_right" style="background-color: #69add5">0.681</td>
<td class="gt_row gt_right" style="background-color: #afd1e7">0.459</td>
<td class="gt_row gt_right" style="background-color: #3484bf">0.548</td>
<td class="gt_row gt_right" style="background-color: #3282be">1.4</td>
</tr>
<tr class="even">
<td class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">6-of-6</td>
<td class="gt_row gt_right">211</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.791</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.149</td>
<td class="gt_row gt_right" style="background-color: #84bcdb">0.251</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.948</td>
<td class="gt_row gt_right">100%</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.938</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.188</td>
<td class="gt_row gt_right" style="background-color: #94c4df">0.313</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.976</td>
<td class="gt_row gt_right" style="background-color: #d9e8f5">0.222</td>
<td class="gt_row gt_right" style="background-color: #a3cce3">0.362</td>
<td class="gt_row gt_right" style="background-color: #2e7ebc">0.6</td>
</tr>
</tbody>
</table>
<figcaption>Table 9: Building-level performance in full: the six products and the six agreement rules in the core region at matching radii of 10, 20 and 30 m. Parentheses at 10 m give each product’s as-delivered value. Crowd-adjusted precision re-judges expert-unmatched flags against the crowd verdicts, credited only where volunteers reviewed the cell; crowd reviewed is the share of each row’s unmatched flags they saw. Visits per find is field visits per damage point reached at 30 m. Shading ranks values within each column.</figcaption>
</figure>

All CEMS-based results in this paper use a 10 m matching radius, and every model is fitted and evaluated at that radius. Because the radius defines the target itself, the whole analysis is re-run at 20 m (widening the positive class: 3,727 labelled buildings against 2,064) and at 30 m (the finding distance).

<a href="#tbl-dial-full" class="quarto-xref">Table 9</a> lists every product and voting rule at all three radii under the paper’s primary scoring; the models’ radius behaviour is summarised below.

Every number rises with the radius, because a flag one or two buildings away from recorded damage starts to count as a hit. The geography null gains fastest: a wider radius spreads each expert point over a cluster of neighbouring buildings, making the target area-shaped, which is exactly the shape a smooth spatial predictor captures well; refit at 30 m the null’s F1 climbs 0.159/0.255/0.336 across the three radii and at 10 m it beats two of the six products. And combination stays ahead at every radius (voting at its best cut 0.323/0.351/0.402, fusion 0.357/0.388/0.432), so the paper’s conclusions do not depend on the radius choice. The tighter 10 m label concentrates the positives onto individual buildings, where per-building discrimination is required, and there the case for *combining* products is at its strongest: the best agreement rule reaches 1.9× the best single product’s F1 at 10 m, against 1.5× at 30 m. Reporting at 10 m is therefore both the more consistent choice and the more demanding one: the reading where a building-level claim means a building.

The matching frame itself (footprint distance on the shared base, Microsoft’s footprints mapped one-to-one) is set out in the [matching appendix](#app-matching); the centroid frame this draft replaced is reproducible from the tagged artefacts and ran lower on every product.

The last check concerns cloud. Only Microsoft publishes a per-building visibility field. Scored against it, the effect is negligible in this event: 3.6% of the buildings Microsoft analysed are mostly obscured, precision is unchanged under any visibility filter, and exactly one missed reference point falls on an obscured building. The model abstains under cloud rather than flagging into it.

### Confidence intervals for the headline numbers

Every interval below is a 95% spatial block bootstrap: H3 cells (res-8 in the core region, 133 blocks; res-7 as-delivered) are resampled with replacement 2,000 times and each statistic is recomputed from the frozen match indicators as a ratio of cell-weighted sums. The same cell draw is shared by every predictor, so differences between predictors are paired. The models are scored from their frozen out-of-fold scores at their frozen operating cuts; nothing is refitted inside the loop, so the intervals measure sampling noise around the reported numbers, not a re-run of the threshold search. Because whole neighbourhoods are resampled, the intervals are wide: one damage cluster entering or leaving the sample moves a product’s precision by more than its decimals suggest, which is worth remembering when reading any two products as “different”.

<figure class="quarto-float quarto-float-tbl figure">
<table class="gt_table cell caption-top table table-sm table-striped small" data-quarto-bootstrap="false">
<thead>
<tr class="gt_col_headings gt_spanner_row header">
<th rowspan="2" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col"></th>
<th colspan="4" id="10-m" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner">10 m</span></th>
<th colspan="2" id="30-m" class="gt_center gt_columns_top_border gt_column_spanner_outer" data-quarto-table-cell-role="th" scope="colgroup"><span class="gt_column_spanner">30 m</span></th>
</tr>
<tr class="gt_col_headings even">
<th id="P10" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">P</th>
<th id="R10" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">R</th>
<th id="F110" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">F1</th>
<th id="Padj" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">P (crowd-adj)</th>
<th id="F130" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">F1</th>
<th id="visits" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">visits/find</th>
</tr>
</thead>
<tbody class="gt_table_body">
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">Microsoft</th>
<td class="gt_row gt_left">0.122 (0.072–0.182)</td>
<td class="gt_row gt_left">0.611 (0.499–0.726)</td>
<td class="gt_row gt_left">0.203 (0.127–0.285)</td>
<td class="gt_row gt_left">0.270 (0.213–0.335)</td>
<td class="gt_row gt_left">0.340 (0.228–0.456)</td>
<td class="gt_row gt_left">6.9 (4.7–11.1)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">IMPACT v2</th>
<td class="gt_row gt_left">0.104 (0.067–0.141)</td>
<td class="gt_row gt_left">0.627 (0.538–0.687)</td>
<td class="gt_row gt_left">0.178 (0.119–0.232)</td>
<td class="gt_row gt_left">0.187 (0.144–0.229)</td>
<td class="gt_row gt_left">0.379 (0.278–0.466)</td>
<td class="gt_row gt_left">9.6 (7.1–14.3)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">OSU</th>
<td class="gt_row gt_left">0.068 (0.046–0.092)</td>
<td class="gt_row gt_left">0.865 (0.819–0.896)</td>
<td class="gt_row gt_left">0.126 (0.086–0.166)</td>
<td class="gt_row gt_left">0.144 (0.116–0.174)</td>
<td class="gt_row gt_left">0.288 (0.212–0.364)</td>
<td class="gt_row gt_left">18.9 (13.8–28.4)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UH</th>
<td class="gt_row gt_left">0.124 (0.071–0.195)</td>
<td class="gt_row gt_left">0.453 (0.359–0.543)</td>
<td class="gt_row gt_left">0.195 (0.120–0.275)</td>
<td class="gt_row gt_left">0.201 (0.129–0.293)</td>
<td class="gt_row gt_left">0.319 (0.211–0.428)</td>
<td class="gt_row gt_left">6.6 (4.2–11.3)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">LIST</th>
<td class="gt_row gt_left">0.086 (0.058–0.113)</td>
<td class="gt_row gt_left">0.755 (0.695–0.795)</td>
<td class="gt_row gt_left">0.154 (0.108–0.198)</td>
<td class="gt_row gt_left">0.164 (0.130–0.196)</td>
<td class="gt_row gt_left">0.342 (0.257–0.422)</td>
<td class="gt_row gt_left">11.9 (9.0–17.5)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UNEP</th>
<td class="gt_row gt_left">0.117 (0.062–0.186)</td>
<td class="gt_row gt_left">0.431 (0.335–0.534)</td>
<td class="gt_row gt_left">0.184 (0.107–0.269)</td>
<td class="gt_row gt_left">0.253 (0.198–0.320)</td>
<td class="gt_row gt_left">0.316 (0.207–0.434)</td>
<td class="gt_row gt_left">6.0 (3.9–10.4)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">1-of-6</th>
<td class="gt_row gt_left">0.053 (0.035–0.073)</td>
<td class="gt_row gt_left">0.952 (0.926–0.969)</td>
<td class="gt_row gt_left">0.100 (0.067–0.135)</td>
<td class="gt_row gt_left">0.128 (0.105–0.151)</td>
<td class="gt_row gt_left">0.239 (0.172–0.307)</td>
<td class="gt_row gt_left">25.8 (18.7–39.5)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">2-of-6</th>
<td class="gt_row gt_left">0.085 (0.057–0.113)</td>
<td class="gt_row gt_left">0.899 (0.857–0.927)</td>
<td class="gt_row gt_left">0.155 (0.107–0.201)</td>
<td class="gt_row gt_left">0.179 (0.149–0.210)</td>
<td class="gt_row gt_left">0.341 (0.255–0.422)</td>
<td class="gt_row gt_left">14.7 (11.0–21.6)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">3-of-6</th>
<td class="gt_row gt_left">0.148 (0.103–0.195)</td>
<td class="gt_row gt_left">0.781 (0.712–0.829)</td>
<td class="gt_row gt_left">0.250 (0.181–0.314)</td>
<td class="gt_row gt_left">0.262 (0.211–0.311)</td>
<td class="gt_row gt_left">0.472 (0.365–0.563)</td>
<td class="gt_row gt_left">7.0 (5.3–9.9)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">4-of-6</th>
<td class="gt_row gt_left">0.268 (0.181–0.355)</td>
<td class="gt_row gt_left">0.566 (0.472–0.654)</td>
<td class="gt_row gt_left">0.364 (0.265–0.445)</td>
<td class="gt_row gt_left">0.416 (0.323–0.522)</td>
<td class="gt_row gt_left">0.562 (0.423–0.664)</td>
<td class="gt_row gt_left">3.0 (2.1–4.2)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">5-of-6</th>
<td class="gt_row gt_left">0.474 (0.348–0.579)</td>
<td class="gt_row gt_left">0.329 (0.223–0.430)</td>
<td class="gt_row gt_left">0.388 (0.282–0.470)</td>
<td class="gt_row gt_left">0.636 (0.478–0.774)</td>
<td class="gt_row gt_left">0.548 (0.417–0.649)</td>
<td class="gt_row gt_left">1.4 (1.0–1.8)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">6-of-6</th>
<td class="gt_row gt_left">0.791 (0.722–0.863)</td>
<td class="gt_row gt_left">0.149 (0.090–0.208)</td>
<td class="gt_row gt_left">0.251 (0.162–0.330)</td>
<td class="gt_row gt_left">0.948 (0.896–0.987)</td>
<td class="gt_row gt_left">0.362 (0.235–0.472)</td>
<td class="gt_row gt_left">0.7 (0.5–0.8)</td>
</tr>
</tbody>
</table>
<figcaption>Table 10: Core region, 95% block-bootstrap intervals. P/R/F1 at 10 m, crowd-adjusted precision (10 m), F1 at 30 m, and visits per find (30 m). The 20 m radius and the as-delivered region are in the frozen artefact (RQ9).</figcaption>
</figure>

<figure class="quarto-float quarto-float-tbl figure">
<table class="gt_table cell caption-top table table-sm table-striped small" data-quarto-bootstrap="false">
<thead>
<tr class="gt_col_headings header">
<th class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col"></th>
<th id="F1" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">F1 at operating point</th>
<th id="diff" class="gt_col_heading gt_columns_bottom_border gt_left" data-quarto-table-cell-role="th" scope="col">F1 − null</th>
</tr>
</thead>
<tbody class="gt_table_body">
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">Microsoft</th>
<td class="gt_row gt_left">0.193 (0.127–0.267)</td>
<td class="gt_row gt_left">+0.034 (-0.013–+0.086)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">IMPACT v2</th>
<td class="gt_row gt_left">0.174 (0.118–0.228)</td>
<td class="gt_row gt_left">+0.013 (-0.023–+0.058)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">OSU</th>
<td class="gt_row gt_left">0.126 (0.087–0.170)</td>
<td class="gt_row gt_left">-0.033 (-0.059–-0.001)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UH</th>
<td class="gt_row gt_left">0.180 (0.117–0.256)</td>
<td class="gt_row gt_left">+0.021 (-0.029–+0.081)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">LIST</th>
<td class="gt_row gt_left">0.151 (0.108–0.198)</td>
<td class="gt_row gt_left">-0.008 (-0.034–+0.027)</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">UNEP</th>
<td class="gt_row gt_left">0.171 (0.105–0.248)</td>
<td class="gt_row gt_left">+0.010 (-0.035–+0.067)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">geography null (logistic)</th>
<td class="gt_row gt_left">0.159 (0.118–0.199)</td>
<td class="gt_row gt_left">—</td>
</tr>
<tr class="even">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">flat k-of-6 voting</th>
<td class="gt_row gt_left">0.323 (0.233–0.399)</td>
<td class="gt_row gt_left">+0.160 (+0.100–+0.221)</td>
</tr>
<tr class="odd">
<th class="gt_row gt_left gt_stub" data-quarto-table-cell-role="th">weighted fusion</th>
<td class="gt_row gt_left">0.357 (0.261–0.429)</td>
<td class="gt_row gt_left">+0.195 (+0.125–+0.255)</td>
</tr>
</tbody>
</table>
<figcaption>Table 11: Model frame (building labels, core region), 95% block-bootstrap intervals: F1 at each predictor’s frozen operating point and its paired difference from the logistic geography null. A difference interval that excludes zero separates from the null; only the combination rules do so upward.</figcaption>
</figure>

In the as-delivered region the product intervals widen further (UH’s precision 0.012 runs 0.005 to 0.025); the full set is in the RQ9 artefact. Two claims elsewhere in the paper depend on these intervals. The 6-of-6 rule’s sub-1 visits per find holds: its interval upper limit is 0.79. And the null-versus-product finding becomes more specific: no product demonstrably adds information beyond geography at its shipped operating point, one (OSU) demonstrably falls short of it, and both combination rules demonstrably exceed it.

### How the crowd adjustment works, and what happened when the crowd voted again

Every crowd-adjusted precision in this paper starts from one simple rule, and <a href="#fig-crowdmech" class="quarto-xref">Figure 14</a> shows it applied to a real street in Catia La Mar. A flagged building with an expert damage point within 10 m counts as a hit outright; the crowd plays no part in that. Every other flag sits inside one of the ~50 m cells that MapSwipe volunteers voted on, and the rule is: if most volunteers who saw that cell said *yes, damaged*, the flag is counted as confirmed damage and improves the adjusted precision; if they said *no* or *not sure*, it stays a false alarm. Flags in cells the volunteers never saw earn nothing: the adjustment is a measurement, not an estimate, so it understates the true precision of products the crowd barely reviewed. The MapSwipe campaign was seeded on the coastal strip’s Microsoft flags, so it reviewed 99% of Microsoft’s unmatched flags but only 26% of UH’s, and <a href="#tbl-dial-full" class="quarto-xref">Table 9</a> states that coverage beside each crowd-adjusted value. An earlier draft instead assumed the unreviewed flags contained damage at the same rate as the reviewed ones; that assumption is not defensible where the reviewed flags are the ones that happened to fall in another product’s zone, and it is dropped throughout (decision record ADR-0031).

The upper bound in <a href="#fig-bounds" class="quarto-xref">Figure 2</a> combines the crowd credit with the *possibly damaged* points as a union: a flag that qualifies under both is counted once. The two additions mostly affect different flags anyway; only 13%–20% of the crowd-confirmed flags sit within 10 m of a *possibly-damaged* point, so the crowd was mainly confirming damage the expert map never recorded rather than re-grading its low-confidence points.

In August 2026, after this paper’s numbers were frozen, the campaign over this strip was run a second time: 728 new volunteers re-judged exactly the same 3,482 cells, and each cell now received about sixteen votes instead of six: a much closer review of the same buildings by different people. Two caveats mean this is not a perfect replication. The answer buttons changed: round 2 offered no “no damage” option, so a volunteer who saw nothing wrong had to press “not sure”, which means round 1’s headline finding for this strip (71% of cells actively judged undamaged) simply cannot be re-measured. And the two rounds showed volunteers different, though similarly dated, satellite images.

What can be compared across the rounds is how much damage the crowd *confirmed*, and that held up. Of Microsoft’s 6,441 flags in this strip with no expert match, the first crowd confirmed 12.7%; the second confirmed 11.1%. Two independent crowds agree that roughly one flag in eight has crowd-visible damage under it. If anything, the closer review confirmed slightly *less*, so the crowd-adjusted values in this paper should be read as sitting a little high, consistent with their stated role as upper estimates.

What did not hold up is *which* cells were confirmed: only about a quarter of the cells the first crowd confirmed were confirmed again by the second (the purple outlines in <a href="#fig-crowdmech" class="quarto-xref">Figure 14</a>). That sounds alarming until one asks how much two small vote samples should agree even if volunteers were perfectly consistent, and the answer is: not much. Six votes on a borderline cell is close to a coin toss, and once that known voting noise is accounted for, the two rounds’ underlying judgements agree well (correlation 0.63, versus 0.29 before the correction). Most of the apparent inconsistency comes from small vote counts, not from volunteers changing their minds. The practical lesson is the one this paper already follows: a single cell’s verdict is too noisy to rely on, but sums over thousands of cells are steady, which is why crowd verdicts appear here only inside aggregate numbers, never as building-level ground truth.

Recomputing each product’s crowd-adjusted precision with the second round’s verdicts in place of the first moves it by at most 0.01 in either direction: Microsoft’s falls from 0.268 to 0.256, UNEP’s from 0.081 to 0.072 (nearly all of its crowd-reviewed flags sit in this one strip), and IMPACT’s and UH’s rise slightly; no product overtakes another.

<figure class="quarto-float quarto-float-fig figure">
<img src="embedded-image" class="img-fluid figure-img" role="img" />
<figcaption>Figure 14: How the MapSwipe crowd enters the precision calculation, and what an independent re-vote changed. Both panels show the same Catia La Mar neighbourhood; hexagons are the ~50 m crowd task cells, tinted by majority verdict. <strong>A</strong>, round 1: a flag matched by an expert point within 10 m is a true positive (green); an unmatched flag in a cell the crowd judged damaged is counted as confirmed and improves the adjusted precision (blue); in a cell judged undamaged or uncertain it remains a false alarm (orange). <strong>B</strong>, round 2, re-voted the identical cells at ~16 votes each, with no “no damage” answer available (its “not sure” absorbs it): purple outlines mark cells whose verdict changed between rounds. Individual cells flip; the total the adjustment depends on barely moves (12.7% → 11.1% of the strip’s unmatched Microsoft flags confirmed).</figcaption>
</figure>

