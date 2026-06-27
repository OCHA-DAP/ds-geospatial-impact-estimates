# Data ingestion ledger

Auto-maintained by the pipeline loaders — a human-readable record of what is in the blob lake. Idempotency lives in the blob layout (see `docs/decisions/0005`); this is the provenance view. Interim Markdown format, portable to a Postgres ledger later.

| source | layer | dataset | path | detail | status | updated |
| --- | --- | --- | --- | --- | --- | --- |
| codab | bronze | OCHA CODAB admin boundaries — VEN (FieldMaps) | ds-geospatial-impact-estimates/bronze/source=codab/adm0=VE | adm0=2; adm1=25; adm2=336; adm3=1135; EPSG:4326 | ingested | 2026-06-26 |
| common | gold | Common-model damage facts (Overture base) | ds-geospatial-impact-estimates/gold/model=common/adm0=VE/facts.parquet | 6,228 rows; sources MS + CEMS on Overture base; exposed/damaged/fraction | ingested | 2026-06-26 |
| common | gold | Common-model damage facts (Overture base, coverage-aware) | ds-geospatial-impact-estimates/gold/model=common/adm0=VE/facts.parquet | 11,590 rows; exposed/analysed/coverage/detected/extrapolated per source | ingested | 2026-06-27 |
| copernicus_ems | bronze | Copernicus EMS EMSR884 — Venezuela earthquake damage products | ds-geospatial-impact-estimates/bronze/source=copernicus_ems/code=EMSR884 | 7 delivered, 11 pending; GRA/GRM; idempotent poll | ingesting | 2026-06-27 |
| copernicus_ems | gold | CEMS EMSR884 damage facts | ds-geospatial-impact-estimates/gold/source=copernicus_ems/adm0=VE/damage_facts.parquet | 258 fact rows; h3 + adm0-3; damage_features + damaged_area_m2 | ingesting | 2026-06-26 |
| copernicus_ems | silver | CEMS EMSR884 damage grading (builtUpA) | ds-geospatial-impact-estimates/silver/source=copernicus_ems/adm0=VE/builtup_damage.parquet | 309 graded blocks; EMS grade + class; EPSG:4326 | ingesting | 2026-06-26 |
| copernicus_ems | silver | CEMS analysed extent (AOI - not-analysed) | ds-geospatial-impact-estimates/silver/source=copernicus_ems/adm0=VE/analysed_extent.parquet | 22 polygons; coverage mask for detected vs extrapolated | ingesting | 2026-06-27 |
| copernicus_ems | silver | CEMS analysed extent (AOI - not-analysed) + coverage detail | ds-geospatial-impact-estimates/silver/source=copernicus_ems/adm0=VE/analysed_extent.parquet | 22 analysed polygons; AOI/not-analysed shapes for display | ingesting | 2026-06-27 |
| microsoft | bronze | Building footprints — Catia La Mar (raw GPKG) | ds-geospatial-impact-estimates/bronze/source=microsoft/adm0=VE/predicted_damage_catia_la_mar_footprints.gpkg | GeoPackage as received from HDX (CC-BY) | ingested | 2026-06-26 |
| microsoft | gold | Damage facts — Catia La Mar | ds-geospatial-impact-estimates/gold/source=microsoft/adm0=VE/damage_facts.parquet | 524 fact rows; h3 + adm0-3; metrics buildings/damaged/fraction | ingested | 2026-06-27 |
| microsoft | silver | Building footprints — Catia La Mar | ds-geospatial-impact-estimates/silver/source=microsoft/adm0=VE/footprints.parquet | 30,761 footprints; binary damaged + damage_pct; EPSG:4326 | ingested | 2026-06-26 |
| microsoft | silver | Building footprints — Catia La Mar + La Guaira + Caraballeda (HDX, CC-BY) | ds-geospatial-impact-estimates/silver/source=microsoft/adm0=VE/footprints.parquet | 46,564 footprints; 3 AOIs; binary damaged + valid-area masks | ingested | 2026-06-27 |
| overture | silver | Overture buildings exposure base (event extents) | ds-geospatial-impact-estimates/silver/source=overture/adm0=VE | ~57,008 buildings this run; release 2026-06-17.0; partitioned by region | ingested | 2026-06-26 |
