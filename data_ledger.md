# Data ingestion ledger

Auto-maintained by the pipeline loaders — a human-readable record of what is in the blob lake. Idempotency lives in the blob layout (see `docs/decisions/0005`); this is the provenance view. Interim Markdown format, portable to a Postgres ledger later.

| source | layer | dataset | path | detail | status | updated |
| --- | --- | --- | --- | --- | --- | --- |
| codab | bronze | OCHA CODAB admin boundaries — VEN (FieldMaps) | ds-geospatial-impact-estimates/bronze/source=codab/adm0=VE | adm0=2; adm1=25; adm2=336; adm3=1135; EPSG:4326 | ingested | 2026-06-26 |
| copernicus_ems | bronze | Copernicus EMS EMSR884 — Venezuela earthquake damage products | ds-geospatial-impact-estimates/bronze/source=copernicus_ems/code=EMSR884 | 4 delivered, 12 pending; GRA/GRM; idempotent poll | ingesting | 2026-06-26 |
| microsoft | bronze | Building footprints — Catia La Mar (raw GPKG) | ds-geospatial-impact-estimates/bronze/source=microsoft/adm0=VE/predicted_damage_catia_la_mar_footprints.gpkg | GeoPackage as received from HDX (CC-BY) | ingested | 2026-06-26 |
| microsoft | gold | Damage facts — Catia La Mar | ds-geospatial-impact-estimates/gold/source=microsoft/adm0=VE/damage_facts.parquet | 316 fact rows; h3 + adm0-3; metrics buildings/damaged/fraction | ingested | 2026-06-26 |
| microsoft | silver | Building footprints — Catia La Mar | ds-geospatial-impact-estimates/silver/source=microsoft/adm0=VE/footprints.parquet | 30,761 footprints; binary damaged + damage_pct; EPSG:4326 | ingested | 2026-06-26 |
