# 0006 — Microsoft merged v3 against the v1 the brief scores

Auxiliary, internal reference. The viewer and the brief keep scoring v1 (the 29 June merged
file), which is what responders had. Nothing here writes to the lake or to `exploratory/paper/`.

## Question

Microsoft sent a v3 of the merged Venezuela file on 2026-09-04. Their description:

- v2 removed 3,912 building footprints that overlapped each other;
- v3 re-thresholds `damaged` to `damage_pct_0m >= 0.8` for records whose primary scene is the
  Catia La Mar Vantor image.

Does the file contain exactly that change, and how does it score against v1 under the paper's
method?

## Data

- v1: `bronze/source=microsoft/adm0=VE/merged/ALL_AOIS_building_predictions_deduplicated.gpkg`
  (72,162 records, 8,410 damaged).
- v3: `ALL_AOIS_building_predictions_deduplicated_v3.gpkg`, received by email, SHA-256
  `2d53b4a14a5723b81ac3f58da2ec8ca49b69876738a220a3cb9d6149ea0a5ef3` (68,250 records, 4,796
  damaged). Not yet landed in the lake; `analysis.py --v3 <path>` reads it locally and checks
  the hash.

## Method

`analysis.py` matches the two files record by record on `source_file` + `orig_id`, maps each
version's damaged footprints onto the Overture base with the paper's one-to-one rule (ADR-0030),
and scores them with the paper's own scorecard functions: points frame, CEMS damaged and
destroyed points, 10 m. Before it scores v3, it reproduces v1 through the same code and stops
unless the mapped ids equal `lib/ms_1to1_ids.csv` (8,339 ids) and the scores equal
`results.csv`. The gate passed.

## Findings

### 1. The file contains exactly the described change

| | records |
|---|---:|
| v1 records | 72,162 |
| removed as duplicates | 3,912 |
| of which flagged damaged in v1 | 61 |
| flags switched off by the re-threshold | 3,553 |
| v3 damaged (8,410 − 61 − 3,553) | 4,796 |

No record was added, no damage score changed, and every switched flag was a 1 → 0 in the
Catia La Mar Vantor scene. In v1 every scene used `damaged = damage_pct_0m > 0`; v3 keeps that
rule everywhere except the Catia La Mar Vantor scene, which now needs 0.8. That scene went from
6,047 to 2,470 damaged records; the other four scenes lost 37 flags between them, all to
deduplication. On the shared base, v3's 4,789 flagged buildings are a strict subset of v1's 8,339.

### 2. Precision rises by half, recall drops by six points

Core region, 10 m:

| | flags | P | R | F1 |
|---|---:|---:|---:|---:|
| v1 | 7,878 | 0.122 | 0.611 | 0.203 |
| v3 | 4,560 | 0.179 | 0.552 | 0.270 |

As delivered, the result is the same (P 0.121 → 0.178, R 0.611 → 0.552), since Microsoft
covers only the Caraballeda CEMS area. At 20 m F1 moves 0.281 → 0.357, at 30 m 0.340 → 0.419.

Microsoft v1 already had the highest core F1 of the six products (UH next at 0.195). v3 would
also have the highest precision (UH 0.124).

### 3. The west strip was the target, and precision there is still low

Caraballeda split at Microsoft's scene boundary (−67.03); the Catia La Mar Vantor scene spans
−67.110 to −66.995, so it covers the west strip:

| | v1 flags | v1 share flagged | v1 P | v3 flags | v3 share flagged | v3 P |
|---|---:|---:|---:|---:|---:|---:|
| west strip | 4,405 | 0.287 | 0.052 | 1,528 | 0.100 | 0.084 |
| east strip | 3,545 | 0.082 | 0.205 | 3,044 | 0.070 | 0.225 |

The over-flagging in the west strip falls from 29% to 10% of buildings, close to the east strip's
share. Precision there improves but stays at well under half the east strip's. By primary scene
(as delivered): Catia La Mar Vantor flags 0.064 → 0.094, other scenes 0.263 → 0.265.

### 4. The single- versus multi-scene precision gap closes

| | v1 flags | v1 P | v3 flags | v3 P |
|---|---:|---:|---:|---:|
| seen in 1 scene | 6,619 | 0.096 | 2,494 | 0.176 |
| seen in 2+ scenes | 1,332 | 0.245 | 2,078 | 0.181 |

In v1 this reproduces the frozen result the brief cites (0.245 against 0.097, scored in the old
centroid frame) in the footprint frame. In v3 the gap is gone: the re-threshold removed the weak
single-scene flags, and deduplication merged former duplicate pairs into multi-scene records,
which brought lower-precision buildings into the 2+ group.

### 5. Agreement rules barely move

The best rule in the core, 5-of-6, goes from F1 0.388 to 0.389; 4-of-6 from 0.364 to 0.383.
Microsoft's removed flags were mostly ones the other products did not share.

## Caveats

- v3 is a correction made after the response, with feedback on the earlier version available.
  We do not know how the 0.8 cut was chosen; if it was set by looking at reference data, the gain
  is partly hindsight. Worth asking Microsoft.
- Recall is lost as well as precision gained: 3,550 buildings stop being flagged, and recall
  falls 0.611 → 0.552.

## What it feeds

Nothing by default. If wanted, the brief's Product updates line "Microsoft's later version: TBD"
could carry one sentence from findings 2 and 3, with numbers wired through `brief_numbers.py`.
