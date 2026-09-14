---
status: "accepted"
date: 2026-09-14
deciders: zackarno
---
# Paper analysis as a Snakemake DAG over one library and one results table

## Context and Problem Statement

The technical brief's numbers were produced by about forty per-research-question scripts under
`exploratory/paper/artefacts/`, each re-implementing the core region, the crowd-verdict
lookup, cell assignment and the precision/recall arithmetic, and each writing its own CSV.
The brief typed the numbers by hand. The ADR-0030/0031 refreeze needed edits in 25 scripts
for one conceptual change and surfaced four inconsistencies that no anchor check compared:
two location conventions, two encodings of "unreviewed" crowd flags, a hard-coded voting
cut and one script already using the convention its siblings did not. Zack's requirement:
numbers must come from standardized outputs, the pipeline must be as simple as possible, and
a change's effect on every number must be verifiable.

## Decision Drivers

* One definition per convention, testable in isolation.
* The brief can only ever quote a computed value.
* Rerun only what changed; never spend an hour of compute on a prose edit.
* Every number change between two states is listed, with declared expectations checked.
* Fewer files to read: the frozen scripts become an archive nobody has to open.

## Considered Options

1. Keep the scripts, add a library and Snakemake on top. Rejected as the end state: the
   duplication that hid the inconsistencies stays.
2. pytask or DVC instead of Snakemake. pytask would have meant rewriting every entry point
   before anything else could be verified; DVC's content hashing of untracked outputs is
   worth adding later, not needed first.
3. Snakemake DAG + a compact library + a handful of modules that write rows of one long
   results table, verified against the frozen scripts' outputs (the oracle) before the
   scripts are archived. Chosen.

## Decision Outcome

* `exploratory/paper/pipeline/paperlib.py` holds the definitions: frame and matching
  (ADR-0030), crowd credit (ADR-0031), regions, reference grades, predictors. Synthetic
  geometry tests pin them.
* `pipeline/scorecards.py`, `pipeline/ranking.py`, `pipeline/facts.py` write rows
  `(region, lens, radius, predictor, metric, value, source)`; `artefacts/consolidate.py`
  merges them with adapters over the frozen heavy chain (fusion, bootstrap, ablation,
  round-2 crowd) into `artefacts/results.csv`, the only file the brief reads.
* `brief_numbers.py` is lookups and formatting over that table; the brief quotes keys inline
  and its tables are generated. `audit_brief_numbers.py` fails the build on a hand-typed
  number outside a short allowlist of dates and design parameters.
* `Snakefile` declares the DAG; the heavy rules do not depend on the library and rerun only
  when named. `diff_results.py --base <ref>` rebuilds the table at any git ref and reports
  every changed value with PASS/FAIL against declared expectations.
* Verification during the migration: each module's rows had to equal the oracle to the
  CSVs' rounding, with every difference explained in `check_against_oracle.py`.

### Consequences

* Good: a convention change is one edit, one `snakemake`, one diff report.
* Good: the frozen scripts stay under `artefacts/` as the archive and the oracle; nothing is
  deleted.
* Bad: Snakemake tracks staleness by modification time, so a `git checkout` can make outputs
  look stale; `snakemake --touch` after verifying a state is the fix. DVC would hash content.
* Neutral: the definitional fix found during migration (rq2i's "confirmed share" divided by
  all unmatched flags, rq5b's by reviewed flags) is recorded as an explained exception.
