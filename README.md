# ds-geospatial-impact-estimates

A viewer and harmonization layer for multi-source, satellite-derived **damage
exposure** data. Built first for a Venezuela earthquake response, designed to
generalize to other events and globally.

The system ingests heterogeneous AI/ML-derived damage data — per-building
damage labels on Microsoft/Google footprints, Copernicus EMS damage polygons,
damage rasters — normalizes them onto a common exposure base and an H3 grid,
aggregates to OCHA COD admin 0/1/2 units, and lets users **compare what
different sources say** for the same unit.

## Architecture at a glance

- **Lake:** Azure Blob, medallion layout (`bronze`/`silver`/`gold`),
  GeoParquet + COG, partitioned `source=…/adm0=…`.
- **Engine:** DuckDB (`spatial` + `azure` + `h3`) as both ETL and serving for
  v1. No PostGIS until concurrent multi-process writes force it.
- **Grid:** H3 as the intermediate harmonization grid; CODs admin as the
  reporting layer.
- **Taxonomy:** damage classes aligned to the xBD Joint Damage Scale (0–3),
  with Copernicus EMS grading carried in parallel.
- **Viewer:** Python-native. Two candidates under evaluation
  (Streamlit + pydeck vs Panel/Solara + Lonboard) — decided by spike.

Key decisions live in [`docs/decisions/`](docs/decisions/).

## Development

```bash
uv sync                       # core + dev
uv sync --group streamlit     # + Streamlit/pydeck spike front end
uv sync --group panel         # + Panel/Lonboard spike front end
cp .env.example .env          # then fill in Azure storage settings
```
