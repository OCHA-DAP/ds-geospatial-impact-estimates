# ds-geospatial-impact-estimates

## Environment & credentials
Assume the environment is already configured — the dev-lake SAS tokens, Azure
account prefix, and other `DSCI_*` / `GIE_*` variables are present (in the shell or
`.env`, loaded by `gie.config`). Run pipelines, scripts, and investigations
directly; don't ask me to confirm credentials first. If one is genuinely missing
the command fails loudly — surface that error rather than pre-empting it with a
question.

## Running Python
Use `uv run` (the venv is uv-managed; the repo's `.python-version` pins a pyenv
version that isn't installed, so a bare `python`/`python3` will fail). ETL and
analysis need the `etl` group: `uv run --group etl python <script>`.
