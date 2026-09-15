# VE earthquake — damage product evaluation

Evaluation of six rapid satellite building-damage products released after the M7.5 Venezuela
earthquake (24 June 2026), scored against three reference datasets with non-overlapping blind
spots. The method is recorded in [ADR-0025](../../docs/decisions/0025-damage-product-evaluation-method.md);
read that first if you are reusing any of this on another event.

## What is here

| file | what it is |
|---|---|
| `manuscript_v3.qmd` | the manuscript — **the keeper** (deck-spined short form; appendix carries the machinery) |
| `manuscript_v2.qmd` | long-form draft, **superseded by v3** (source of v3's appendix) — do not edit |
| `findings.qmd` | running register of every analysis, including negative and superseded results |
| `satellite_damage_evaluation_deck_v2.qmd` | current 20-slide results deck |
| `satellite_damage_evaluation_v1.qmd` | earlier deck, **numbers predate the corrections** — do not present |
| `manuscript_draft.qmd` | v1 manuscript, superseded by `manuscript_v2` |
| `manuscript_brief.qmd` | the technical brief — **the keeper since 2026-09**; every number is an inline key from `results.csv` |
| `Snakefile` | the analysis DAG (ADR-0032). Its header is the runbook and the glossary of RQ0–RQ9; start there |
| `pipeline/` | the live analysis: `paperlib.py` (definitions), `scorecards.py`, `ranking.py`, `facts.py` (rows of the results table), `consolidate.py`, the exporters, figure scripts, checks, tests |
| `lib/` | data loaders and the paper's pins (`gie_paper.py`), the three footprint id lists and their manifest |
| `frozen/` | signed-off copies of the archived heavy chain's outputs, with `MANIFEST.csv` (source, commit, sha256, date) |
| `results.csv` | the one table the brief reads (region, lens, radius, predictor, metric, value, source) |
| `brief_numbers.py` | named, formatted values over `results.csv`; the brief quotes them as `{python} N["key"]` |
| `review/` | Tristan's audit export, the refactor checklist, number diffs against earlier states |
| `artefacts/` | **archive**: the ~40 per-RQ scripts that produced the first frozen numbers, their outputs, the oracle. Nothing in `snakemake all` reads from it |
| `timeline/` | product availability timeline (reads `timeline_events.csv`) |

Rendered HTML is **not** tracked. This repo is public and a built deck is a publication, so
`exploratory/paper/*.html` is gitignored and publishing one is a deliberate act. The build
*inputs* (`gie_slides.scss`, `hdx-bg.html`, `password.html`) are tracked.

## Rebuilding the brief (the current path)

```bash
uv run --group etl --group paper snakemake -s exploratory/paper/Snakefile -d exploratory/paper -n        # what is stale
uv run --group etl --group paper snakemake -s exploratory/paper/Snakefile -d exploratory/paper -c2 all   # build
uv run --group etl --group paper snakemake -s exploratory/paper/Snakefile -d exploratory/paper diff --config base=origin/v1
```

The Snakefile header explains rules, staleness, the pipeline's shape and the research questions.
Before `--unlock`, check `pgrep -f "snakemake -s"`: a lock error is also what a healthy running
build produces. The heavy archived chain is re-run only on request (`heavy --forcerun rq8 rq8b`,
then `vendor` to sign its outputs into `frozen/`).

The polygon frame reads the Overture base from the gold pipeline's local cache, `/tmp/gie_base_local`.
macOS empties `/tmp` of files untouched for three days, so after a quiet stretch every rule that
loads buildings fails with "needs the Overture base cache". Rebuild it with the pipeline's own
downloader (a few minutes; it verifies the local set against blob):

```bash
uv run --group etl python -c "import sys; sys.path[:0] = ['pipelines', 'exploratory/paper/lib']; import gie_paper as gp; from harmonize_common import _local_base; print(_local_base(gp.S))"
```

## Rebuilding the older documents

Everything is pinned to the **2026-07-15** data snapshot. Analysis scripts read the Azure data
lake, so they need the usual `DSCI_*` / `GIE_*` environment (see the repo CLAUDE.md); the docs
themselves only need the pre-built figures.

Render a document — note that Quarto needs to be pointed at a Python that has the notebook
stack, which the project venv does not:

```bash
cd exploratory/paper
uv run --group etl --with nbformat --with nbclient --with ipykernel \
       --with matplotlib --with numpy --with shapely --with great-tables bash -c \
  'QUARTO_PYTHON="$(python -c "import sys; print(sys.executable)")" \
   quarto render manuscript_v2.qmd --to html'
```

Re-run an analysis (slow — most reload ~400k buildings from blob and refit spatially-blocked
CV):

```bash
uv run --group etl --with scikit-learn --with scipy --with matplotlib python \
  exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8_learned_fusion.py
```

Figure-only scripts read the CSVs and take seconds, so restyle with these rather than refitting:
`rq8_best_f1_fig.py`, `rq3f_null_ranking_fig.py`, `timeline/plot_timeline.py`.

## Conventions that will bite you if ignored

- **One matching radius: 10 m.** Every CEMS-based number uses it. A 20 m radius changes every
  precision by 1.6–2.2×, so numbers from different radii are never comparable. The fusion is
  fitted *and* evaluated within one radius per frame — the reported numbers are the 10 m fit;
  the 20 m refit (twice the positives, kept as a sensitivity check) is in the manuscript
  appendix.
- **OSU is pinned to v0.** The provider shipped v1 after the freeze and gold/platinum silently
  moved to it. All paper numbers read gold through `gp.building_flags()`, which re-derives OSU
  from silver `version=v0`. The dashboard serves v1 — do not "fix" the mismatch.
- **Precision is a floor, recall is a ceiling.** The expert reference is destruction-biased
  (94% of destroyed vs 49% of damaged buildings captured), so measured precision understates
  and measured recall flatters.
- **No average precision for a single product.** A binary flag list's AP is
  `P·R + (1−R)·prevalence`, not its precision, and is not comparable to a continuous score's AP.

## Environment overrides

| variable | effect |
|---|---|
| `GIE_LABEL_R` | matching radius for the RQ8 scripts (default 10 — the reported frame; pass `20` for the appendix sensitivity refit). Outputs always carry an explicit `_r<N>` suffix. |
| `GIE_SCOPE` | `caraballeda` restricts RQ3f to that AOI, the sharper within-damage-zone ranking test |
