# 0005 — SAR precursors to the 2026-08-26 Langtang Lirung glacier collapse

**Question.** The 2026-08-26 02:52:10 UTC ice/rock detachment on the north flank of
Langtang Lirung (Nepal) sent a debris flow ~100 km down the Lende Khola → Trishuli,
with 300+ confirmed dead and a seismic signature equivalent to M5.2 (USGS
`us7000tbwb`; a second M4.2-equivalent collapse, `us7000tc90`, followed ~3 h later).
Do freely available Sentinel-1 SAR backscatter series show anything anomalous on
that face in the weeks before?

**Method.** Two scripts, run 2026-08-28 (two days after the event):

- `extract.py` (GEE, S1 GRD IW VV+VH, per relative orbit — 19 desc / 85 asc /
  121 desc; descending passes ≈ 06:03 local, ascending ≈ 18:06):
  1. mean backscatter per acquisition 2020-01→now over a 2×3 km **source box**
     covering the published detachment coordinates (Petley/eos.org: 28.28532 N
     85.52515 E and 28.2765 N 85.5194 E) and two elevation/slope-matched **control
     boxes** on the same massif (source 4 973 m / 40°; controls 4 990 m / 39.5°
     and 4 908 m / 37°);
  2. a post-event change map (orbit 85, 2026-08-28 scene vs Jun–Aug 2026 stack) to
     locate the actual scar;
  3. per-pixel z maps of every Jun 1–Aug 24 2026 acquisition against the same
     orbit's 2023–25 monsoon stack.
- `analysis.py`: seasonal climatology z (each 2026 acquisition vs prior years
  within ±12 days of the same day-of-year), source-minus-controls differencing,
  scar-pixel statistics; figures to `figs/` (regenerate by running).
- `offset_tracking.py`: speckle offset tracking (windowed phase cross-correlation,
  640 m windows, 1/10-px subpixel) on the last two pre-event GRD pairs per morning
  orbit, with one-cycle-earlier reference pairs as the noise floor.
- `falsealarms_extract.py` + `falsealarms_analysis.py`: the prospective test —
  45 'Langtang-like' faces from GLIMS (0.5–15 km², mean elev ≥ 4 800 m, GLO30
  mean slope ≥ 25°, deduped per glac_id) across 84.9–86.3°E / 27.9–28.7°N, same
  per-orbit morning-pass series, detector replayed on every face-season.

## Findings

**1. The published coordinates check out.** The post-event |z|≥3 change centroid
inside the source box sits at 28.28648 N 85.52284 E — **260 m** from Petley's early
coordinate. Total |z|≥3 area in the 10×10 km map is 9.4 km² (scar + runout down
the upper Lende valley); 1.06 km² falls inside the source box.

**2. There *is* a face-wide precursor signal — and it is time-of-day dependent.**
Against six prior years (2020–25), the source face in 2026:

- melted out **3–4 weeks earlier** than any prior year on the morning
  (descending) orbits, diverging from the day-of-year envelope from **mid-April**;
- sat **1–2 dB below every prior monsoon** through Jun–Aug (whole-box climatology z,
  last five pre-event acquisitions per orbit):

  | orbit (local time) | last five pre-event z (VV) |
  |---|---|
  | 19 (06:03) | 07-07 −3.1 · 07-19 −1.5 · 07-31 −2.0 · 08-12 −3.7 · 08-24 −2.1 |
  | 85 (18:06) | 06-29 −1.5 · 07-11 +0.3 · 07-23 −1.2 · 08-04 −0.8 · 08-16 −0.8 |
  | 121 (06:03) | 07-02 −5.4 · 07-14 −2.0 · 07-26 −5.6 · 08-07 −3.5 · 08-19 −3.1 |

- Jun–Aug means: source −2.33σ vs controls −0.77/−1.00σ — the face is an outlier
  on its own massif, so this is not just a warm 2026.

After removing valley weather entirely (source − mean(controls), scored against
the prior-year distribution of that same difference), the morning orbits show a
**sustained face-specific departure ≤ −2σ from 2026-07-02** — eight weeks before
the collapse (orbit 121; orbit 19 intermittently from late June). The evening
orbit 85 never leaves its envelope pre-event.

The asymmetry is the physically interesting part: evening passes see a wet
melting face in any monsoon, so they can't distinguish 2026; morning passes
normally see an overnight-refrozen surface. A morning-only backscatter
depression means **the face was staying wet overnight** — consistent with an
anomalously warm/melt-loaded hanging glacier, the mechanism commentators have
speculated about, visible in free SAR data months ahead.

**3. No scar-localised precursor.** Inside the source box, the share of |z|≥2
pixels within the future scar tracks the share outside it on every orbit and
every pre-event date (e.g. final acquisitions: 10.4 % vs 10.9 % on orbit 19).
Amplitude data flagged *which face* was anomalous, not *which 1 km² would fail*,
and showed no terminal acceleration in the last pre-event pass (08-24, 39 h
before, z_d ≈ −1.5). Detecting the failing block itself would need InSAR
coherence/offset tracking (SLC — outside GEE) or higher-resolution tasking.

**3b. No detectable pre-failure sliding either (offset tracking).** Speckle
tracking on the final pre-event pairs (orbit 19: 08-12→08-24, ending 39 h before
collapse; orbit 121: 08-07→08-19) against one-cycle-earlier reference pairs:
whole chips carry a 2–6 m common co-registration offset between GRD products
(reference pairs are *worse* than final pairs, confirming it is systematic, not
motion), and after removing the surround's median shift vector the face's
differential displacement is median 1.4 m / p90 4.1 m in the final pairs —
at or below the reference pairs' own noise (median 2.0 m / p90 4.2 m).
Correlation held on 220–221 of 221 face windows, so this is a measured null,
not a failure to measure: **no sliding above ~2 m per 12 days at 640 m window
scale, up to 39 h out.** Consistent with a melt-driven sudden detachment rather
than weeks of slow creep — and more support for the melt proxy over motion
methods for this failure type (fig `figs/offset_tracking.png`).

**4. The false-alarm test: ~1.3 % of face-seasons fire; the collapse is caught.**
Replaying the detector prospectively — leave-one-out climatology per face ×
descending orbit, minus the same-date fleet-median z (the "everyone else"
control), alarm = 3 consecutive monsoon acquisitions ≤ −2σ:

| threshold | fleet false-alarm rate (226 face-seasons, 2022–26) | detachment box 2026 (stat −3.05) |
|---|---|---|
| −1.5σ | 2.2 % | caught |
| −2.0σ | 1.3 % (3 alarms) | caught |
| −2.5σ | 0.4 % (1 alarm) | caught |

Two structural findings ride along:

- **Scale matters.** At whole-glacier scale (the 10 km² GLIMS polygon) the
  source glacier scores only −1.5 and is *missed* — the face-wide anomaly
  dilutes. The detector needs face-scale AOIs (km-scale tiles over steep
  glacier zones), which multiplies the number of tested units and would raise
  the effective false-alarm count accordingly; the 1.3 % is per *glacier*, and
  is therefore a lower bound on an operational tile-level rate. The detachment
  box is also a hand-drawn 6 km² AOI while the fleet are inventory polygons —
  a further asymmetry in the positive control's favour.
- **The one 2026 fleet alarm is not obviously false.** G085489E28568N
  (28.57°N 85.49°E, Tibet side, same Lende/Kyirong drainage, ~32 km north of
  Langtang Lirung) shows a far stronger signal than the collapse face itself
  (−7.5σ sustained, pre-event data only). Either the same regional melt
  forcing expressed harder on that face, or it is a face genuinely worth
  watching right now. The two 2024 alarms (−2.1, −2.4 nearby in the Shishapangma
  area) had no known collapse and count as false.

**5. Phase-0 historical replay: the pre-registered gate FAILS as written.**
`historical_replay.py` ran the detector (90-day pre-event window, otherwise
identical spec) over the S1-era detachment inventory, with scar locations
re-derived from post-event change where the archive allows:

| event | date | source stat | verdict | fleet alarms |
|---|---|---|---|---|
| Aru-1 (Tibet) | 2016-07-17 | — | not testable — S1 has ~1 scene over W Tibet before 2017 | 0/91 |
| Aru-2 (Tibet) | 2016-09-21 | — | not testable (same archive gap) | 0/96 |
| Sedongpu (SE Tibet) | 2018-10-16 | −1.92 | missed at −2.0 (caught at −1.5) | 0/175 |
| Chamoli (India) | 2021-02-07 | +0.81 | missed — **as predicted** (winter failure, no melt signature) | 8/221 |
| Marmolada (Alps) | 2022-07-03 | +0.31 | missed — no signal at all | 0/70 |

The gate said "catch ≥ 2 of the 3 melt-driven positives, otherwise publish the
negative result": 0 of 2 testable melt-driven events cleared −2σ. Reported as
such. The honest nuances that survive the failure:

- **As a ranker, Sedongpu works**: −1.92 is that face's worst year by a wide
  margin (next: −0.5) — rank 1 of 7 seasons, and an alarm at −1.5σ. Its test is
  also uniquely biased *against* detection: the leave-one-out baseline is
  post-collapse years, and the Sedongpu basin kept failing and eroding
  (~335 M m³ after 2018), so "normal" for that box is itself dark and disturbed.
  A pre-event-only baseline is impossible (archive starts 2017).
- **Chamoli confirms the scope boundary exactly as pre-registered** — a winter
  rock/ice failure carries no melt signature, and the event year isn't even
  negative. (Its 3.6 % fleet alarm rate in Nov–Feb windows also says the
  detector is a melt-season tool; winter windows are noisier.)
- **Marmolada is a magnitude lesson, not just a miss**: a ~6.4×10⁴ m³ serac fall
  is 3–4 orders smaller than Langtang/Sedongpu (10⁷–10⁸ m³) — sub-resolution
  for a 2.4 km box mean, the same dilution physics as finding 4. The detector's
  plausible scope is *giant glacier detachments*, not serac falls.
- Within that scope the honest tally is: Langtang caught (−3.05), Sedongpu
  rank-1/near-miss under an adverse baseline, Aru untestable, Chamoli a
  confirmed out-of-scope null, Marmolada out of scope by magnitude. Suggestive
  for large detachments, nowhere near demonstrated skill — and the S1 archive
  supplies only two testable large melt-driven positives in total, so the
  method may be unvalidatable to operational standard on historical data alone.

**6. Facet enumeration works, at a sensitivity cost.** `facets_prototype.py`
computes the monitoring unit instead of curating it: GLIMS ice + 200 m headwall
buffer ∩ GLO30 slope ≥ 25° ∩ elevation ≥ 4 500 m, aspect smoothed with a 300 m
circular mean and split into octants, components ≥ 0.25 km², 0.5–4 km² enforced
client-side. For the Langtang test region: 580 facets (573 km², median
0.77 km²). Three facets overlap the detachment box; the best-overlapping one
(F00182, 1.84 km², 0.68 km² overlap) scores **−2.07 in 2026 — caught at −2,
its only sub-−2 season** (next-worst −0.9), with a facet-fleet alarm rate of
**2.4 %** per facet-season (5/210) — worse than the glacier-level 1.3 %, as
expected from smaller/noisier units. The catch is thinner than the hand-drawn
box (−3.05) because the anomaly straddles facet boundaries: facet size and the
aspect-splitting rule are a real sensitivity/precision tuning axis, and two
lessons are already concrete — pixel-level elevation floors must be lower than
glacier-mean floors (the scar centroid sits at 4 704 m), and post-event change
centroids are biased downslope, so facet-to-event assignment should use overlap
with the source zone, not point membership.

**7. The Sedongpu miss was an aggregation artefact; Marmolada's was not.**
Review of finding 5 hypothesised the misses were measurement setup, not
detector physics. `miss_retest.py` tests both:

- **Sedongpu, retested at the operational unit scale** (65 ~1.3 km tiles over
  the full post-event change zone, fleet-median adjustment unchanged): two
  tiles over the detachment alarm pre-event — **T59 −2.51, T55 −2.06: caught.**
  The multiple-testing guard passes: the min-over-65-tiles statistic in the six
  non-event years never reaches −2 (worst −1.8, 0/6), so watching 65 units is
  quiet in quiet years and loud in 2018. The finding-5 miss was one 2.4 km box
  averaging over a ~4 km detachment — the same dilution physics as finding 4,
  which the facet design (finding 6) exists to fix.
- **Marmolada, retested with a ~400 m micro-box on the published serac**: −0.40
  in the collapse season, indistinguishable from any other year (0/9 non-event
  years fire either). Not an aggregation artefact — there is no morning-pass
  melt anomaly at any scale GRD can see. Stays out of scope
  (mechanism/magnitude), as does Chamoli (winter).

**Revised Phase-0 tally at the operational (tile/facet) scale:** both testable
in-scope giant melt-season detachments are caught — Langtang 2026 (hand box
−3.05, auto facet −2.07) and Sedongpu 2018 (tile −2.51, guard clean) — with
Chamoli the confirmed out-of-scope null and Aru untestable. The gate *as
originally written* still failed at the original box scale and that record
stands; the retest shows the failure was in the experiment's unit of
aggregation, which the pre-declared facet design already addresses. The
structural limit is unchanged: two positives cannot demonstrate skill, and
prospective seasons remain the only real validation.

## Caveats

- Backscatter on a 40° Himalayan face carries layover/foreshortening; per-orbit
  separation avoids mixing geometries, and both controls share aspect/slope, but
  absolute dB levels between orbits are not comparable.
- The climatology pools six prior years; a monotonic multi-year warming trend
  would appear as a negative z without being 2026-specific. The raw day-of-year
  plot (`figs/raw_vv_doy.png`) shows 2026 clearly below *all* six years, not the
  bottom of a drifting fan — the signal is 2026-specific.
- "Precursor" here means an anomalous surface state, established retrospectively
  with the detachment site known. The false-alarm replay (finding 4) is the
  first-order prospective check, but it covers one region and five seasons with
  exactly one collapse — a single true positive proves feasibility, not skill.
  The 2024 alarms also show the detector fires on non-collapsing faces in warm
  anomalies; any operational use would be as a watch-list ranker, not a siren.

## What it feeds

Nothing operational yet — a side investigation prompted by the event. With the
false-alarm replay at ~1.3 % per glacier-season (and the positive control
caught at every threshold tried), the morning-pass anomaly is plausible as a
cheap GEE-scale *watch-list ranker* for steep glacier faces — a pre-event
complement to the team's CEMS/IMPACT damage-mapping stack. Open items before
anyone leans on it: face-scale tiling (whole-glacier AOIs miss the signal),
more regions/years for a real skill estimate, and a look at the Tibet-side
face currently alarming at −7.5σ.

## Reports

Two self-contained HTML write-ups (figures embedded) build from
`reports/build_reports.py` into `data/`: a technical report and a plain-language
explainer. Live copies are published as claude.ai artifacts (account-private):
technical <https://claude.ai/code/artifact/46583ce9-208b-4d4e-ab86-2f12774352c4>,
explainer <https://claude.ai/code/artifact/8370a6df-724a-4a24-85fd-ea7e40065340>.

## Sources

- Petley, The Landslide Blog (eos.org), 2026-08-27 — coordinates and event
  description: <https://eos.org/thelandslideblog/26-august-2026-nepal-and-tibet>
- USGS Landslide Hazards event page: <https://www.usgs.gov/programs/landslide-hazards/science/2026-nepal-debris-avalanche-and-flash-flood>
- EarthSky (seismic timing/magnitude): <https://earthsky.org/earth/nepal-flash-flood-glacier-collapse-landslide-aug-26-2026/>
- Nature news: <https://www.nature.com/articles/d41586-026-02716-w>
