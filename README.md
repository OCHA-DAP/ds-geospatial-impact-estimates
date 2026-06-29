# ds-geospatial-impact-estimates

A viewer and harmonization layer for multi-source, satellite-derived **damage
exposure** data. Built first for a Venezuela earthquake response, designed to
generalize to other events and globally.

The system ingests heterogeneous AI/ML-derived damage data — Microsoft AI
per-building damage labels, Copernicus EMS rapid-mapping damage, and the IMPACT
Initiatives Sentinel-1 SAR damage proxy — normalizes them onto a common Overture
building base and an H3 grid, aggregates to OCHA COD admin 0/1/2/3 units, and
lets users **compare what different sources say** for the same unit.

## Architecture at a glance

- **Lake:** Azure Blob, medallion layout (`bronze`/`silver`/`gold`),
  GeoParquet (+ source rasters), partitioned `source=…/adm0=…`.
- **Engine:** DuckDB (`spatial` + `azure` + `h3`) as both ETL and serving for
  v1. No PostGIS until concurrent multi-process writes force it.
- **Grid:** H3 as the intermediate harmonization grid; OCHA CODs admin as the
  reporting layer; Overture footprints as the exposure base.
- **Taxonomy:** damage aligned across sources to the Copernicus EMS grades
  (Possibly / Damaged / Destroyed); the SAR z-score thresholds are mapped onto
  the same scale (see [ADR-0008](docs/decisions/)).
- **Viewer:** FastAPI serving DuckDB-over-blob, with a Vite + TypeScript SPA
  (MapLibre GL + deck.gl) front end. Deployed on Azure App Service
  (staging + production slots).

Key decisions live in [`docs/decisions/`](docs/decisions/).

## Development

```bash
uv sync                 # core + dev
uv sync --group api     # + FastAPI serving layer
uv sync --group etl     # + ingestion / harmonization pipelines
cp .env.example .env    # then fill in Azure storage settings

cd web && npm install   # front end deps
npm run dev             # vite dev server   (npm run build to bundle)
```
