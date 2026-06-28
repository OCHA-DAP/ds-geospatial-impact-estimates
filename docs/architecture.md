# Architecture — current stack & network

How data flows from public sources to the browser today. The ETL pipeline runs
offline (locally / on demand); the app reads the published `gold` layer live from
blob. See [roadmap.md](roadmap.md) for where this is heading.

```mermaid
flowchart LR
    subgraph sources["Data sources (public)"]
        ms["Microsoft footprints<br/>(HDX)"]
        cems["Copernicus EMS<br/>(rapid mapping)"]
        ovt["Overture buildings"]
        cod["OCHA COD admin"]
    end

    subgraph etl["ETL pipeline · offline (uv + DuckDB)"]
        direction LR
        ingest["ingest"] --> bronze[("bronze")] --> silver[("silver")] --> gold[("gold ·<br/>common model")]
    end

    blob[("Azure Blob ·<br/>GeoParquet medallion lake")]

    subgraph app["Azure App Service · Linux (one origin)"]
        api["FastAPI + DuckDB<br/>reads gold from blob"]
        spa["Vite SPA ·<br/>MapLibre + deck.gl"]
        api --- spa
    end

    browser["Browser<br/>(+ HTTP cache)"]
    basemap["CARTO / Esri<br/>basemap tiles"]

    sources --> etl --> blob
    blob -->|"DuckDB azure ext · TLS + SAS"| api
    browser <-->|"HTTPS · public"| app
    basemap -->|tiles| browser

    subgraph cicd["CI/CD"]
        gh["GitHub Actions ·<br/>push to v1"] --> stg["staging slot"]
        stg -->|"approval gate"| prod["production slot"]
    end
    cicd -.->|deploys| app
```

**Notes**
- **One app, one origin:** FastAPI serves both `/api` and the built SPA, so there
  are no CORS hops in production.
- **Data path:** the app never bulk-downloads — DuckDB's `azure` extension reads
  GeoParquet with column/row-group pruning and HTTP range requests, authed by a
  read SAS.
- **Trust boundaries:** the browser↔app hop is public HTTPS; the app↔blob hop is
  server-side over TLS with a SAS. Basemap tiles come straight from CARTO/Esri to
  the browser (their own CDN).
- **Deploys** are code-only (build → staging → approval → prod); **data refreshes**
  update `gold` in blob and only need an app restart, no deploy.
