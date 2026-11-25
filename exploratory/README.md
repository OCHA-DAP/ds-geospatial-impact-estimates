# Exploratory

Dated, reproducible **lab-notebook** entries for data/analysis questions we dig
into — the *evidence*, kept separate from the *decisions* it feeds.

## Exploratory analysis vs. ADR

- An entry here answers a question with data: *"is X actually true, and how do we
  know?"* It carries the method, the code, and a conclusion. It is evidence.
- An **ADR** (`docs/decisions/`) records a *decision* with trade-offs: *"given what
  we found, we will do Y."*

The link runs one way: an ADR **cites** the exploration that justifies it. When a
finding changes what we do, update (or supersede) the relevant ADR and point it
back here.

## Layout — one folder per entry

```
exploratory/
  NNNN-short-title/
    analysis.py     # runnable; prints the numbers, saves any figures to figs/
    findings.md     # the writeup: question, method, findings, what-it-feeds
    figs/           # generated figures — GIT-IGNORED, regenerate by running
```

- **Committed:** `analysis.py` (source) + `findings.md` (prose). That's the record.
- **Not committed:** anything generated — `figs/` and caches are git-ignored.
  Figures are a "run it to see" extra, so `findings.md` carries the evidence as
  **text and tables**, not embedded images.
- We use plain `.py` + `.md` over a notebook (`.ipynb` is JSON — noisy diffs,
  hidden state) or Quarto (HTML output, awkward to read/diff).

## Running

```sh
uv run --group etl --with scipy python exploratory/0001-microsoft-overture-duplicates/analysis.py
```

Needs the dev-lake env the pipelines use — `GIE_BLOB_ACCOUNT_PREFIX` +
`DSCI_AZ_BLOB_DEV_SAS` (see `gie.config`). `analysis.py` puts the repo's `src/` on
`sys.path`, so `from gie import ...` works. Read from the **immutable bronze/silver
snapshots** (`docs/decisions/0005`) so a finding can be re-derived later.

## Conventions

- Folder `NNNN-short-title`, zero-padded, incrementing. Independent of ADR numbers;
  cross-reference by path.
- Structure `findings.md`: **Question → Data → Method → Findings → What it feeds.**

## Deployment

This tree is exploratory, not app code — the v1 deploy workflow's `paths-ignore`
skips `exploratory/**`, so nothing here triggers a deployment.
