# Pipelines

ETL over the medallion layout in Azure Blob, run with DuckDB (`gie.db.connect`).

```
bronze/   raw, as-received per source (never mutated; audit trail)
silver/   normalized to a common schema, cleaned, partitioned source=…/adm0=…
gold/     aggregated damage-fact table, ready for the viewer
```

Each source gets a small **adapter** that turns its native format (building
footprints with damage attributes, Copernicus EMS polygons, damage rasters)
into the common silver schema, then into the gold damage-fact table at the H3
grid and admin levels. See `docs/decisions/0001` for the harmonization model
and `docs/decisions/0002` for the engine/storage rationale.

Adapters land here as they are built (`microsoft.py`, `copernicus_ems.py`, …).
