# RQ4 — UNEP debris via enclosed hard-hit admin + 4-way common-coverage comparison

Script `scripts/rq4_enclosed_admin.py` · `rq4_enclosed_summary.csv` · `figs/rq4_enclosed_4way.png`.

## Setup
UNEP debris has no analysed AOI. Region = **6 hard-hit adm3 parroquias** (≥30 CEMS damage points:
Caraballeda, Catia la Mar, La Guaira, Macuto, Urimare, Urbana Morón) **∩ CEMS analysed extent** =
**68.5 km², 1,455 CEMS damage+destroyed points**. STATED ASSUMPTION: UNEP fully covers this
built-up strip in these hard-hit districts (the one place its missing AOI doesn't bite).
Bonus: this is a COMMON coverage → all 4 sources compared on identical ground (unlike RQ2/RQ3
where each used its own AOI). Dual-anchor, r=10 m, CEMS positive {2,3}.

> Enclosure lesson: do NOT gate on fraction of parroquia AREA inside CEMS extent — adm3 units are
> huge & mostly mountain (Caraballeda is only 11% inside). Select hard-hit units, then intersect
> with the CEMS extent (the built-up strip).

## 4-way result (identical coverage)
| source | dmg flagged | recall | precision | F1 | over-det | H3 rank ρ |
|---|---|---|---|---|---|---|
| **OSU** | 22,366 | **0.851** | 0.077 | 0.140 | 15.4× | **0.580** |
| IMPACT v2 | 9,971 | 0.624 | 0.110 | 0.187 | 6.9× | 0.572 |
| Microsoft | 7,539 | 0.608 | 0.126 | 0.209 | 5.2× | 0.418 |
| **UNEP debris** | 7,309 | **0.427** | 0.120 | 0.187 | 5.0× | 0.305 |

## Findings
1. **UNEP is the conservative, lowest-skill detector here:** lowest recall (0.43 — catches <half of
   CEMS damage/destroyed) AND weakest prioritization (ρ 0.31). Debris-mass modelling flags a
   smaller, differently-distributed set (~7.3k, like MS) — it is a distinct signal, not a damage
   classifier, and it shows.
2. **Clean cross-source ordering (now that coverage is identical):**
   recall OSU (0.85) ≫ IMPACT (0.62) ≈ MS (0.61) > UNEP (0.43);
   prioritization OSU (0.58) ≈ IMPACT (0.57) > MS (0.42) > UNEP (0.31).
3. **Common-region matters:** IMPACT's rank skill rises (0.30 on full swath → 0.57 here) because
   it's restricted to hard-hit built-up where it performs; MS dips (0.47 → 0.42). Confirms the
   per-AOI numbers (RQ2/RQ3) are not directly cross-comparable; RQ4 is the fair head-to-head.

## Caveats
- UNEP full-coverage-of-hard-hit assumption is unverifiable (no AOI) — stated, not proven.
- UNEP recall may be mildly conservative if debris_tonnes>0 misses lightly-damaged CEMS points;
  threshold sensitivity untested (all rows have debris>0 so "damaged" = all).
- Still Caraballeda-weighted (609+438 of 1,455 points). Per-unit split would sharpen it.
- Same H3 rank caveat as RQ3: establishes skill, not the noise-vs-bias verdict (needs residual
  Moran's I + covariates).
