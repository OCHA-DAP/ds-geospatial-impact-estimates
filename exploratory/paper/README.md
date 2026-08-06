# VE earthquake — damage product evaluation

Evaluation of six rapid satellite building-damage products released after the M7.5 Venezuela
earthquake (24 June 2026), scored against three reference datasets with non-overlapping blind
spots. The method is recorded in [ADR-0025](../../docs/decisions/0025-damage-product-evaluation-method.md);
read that first if you are reusing any of this on another event.

## What is here

| file | what it is |
|---|---|
| `manuscript_v2.qmd` | the technical write-up — **the keeper** |
| `findings.qmd` | running register of every analysis, including negative and superseded results |
| `satellite_damage_evaluation_deck_v2.qmd` | current 20-slide results deck |
| `satellite_damage_evaluation_v1.qmd` | earlier deck, **numbers predate the corrections** — do not present |
| `manuscript_draft.qmd` | v1 manuscript, superseded by `manuscript_v2` |
| `artefacts/<RQ>/scripts/` | one script per research question; each writes CSVs + `figs/` |
| `artefacts/<RQ>/*.csv` | frozen outputs — the numbers quoted in the docs |
| `timeline/` | product availability timeline (reads `timeline_events.csv`) |

Rendered HTML is **not** tracked. This repo is public and a built deck is a publication, so
`exploratory/paper/*.html` is gitignored and publishing one is a deliberate act. The build
*inputs* (`gie_slides.scss`, `hdx-bg.html`, `password.html`) are tracked.

## Rebuilding

Everything is pinned to the **2026-07-15** data snapshot. Analysis scripts read the Azure data
lake, so they need the usual `DSCI_*` / `GIE_*` environment (see the repo CLAUDE.md); the docs
themselves only need the pre-built figures.

Render a document — note that Quarto needs to be pointed at a Python that has the notebook
stack, which the project venv does not:

```bash
cd exploratory/paper
uv run --group etl --with nbformat --with nbclient --with ipykernel \
       --with matplotlib --with numpy --with shapely bash -c \
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
