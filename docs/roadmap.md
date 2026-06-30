# Roadmap — speed, scale & slickness

Where the [current stack](architecture.md) goes as audience and data volume grow.
**v2 client-side serving** (PMTiles + hyparquet,
[ADR-0011](decisions/0011-v2-client-side-serving-on-app-service.md)) is now shipping
on the existing App Service. The phases below finish that migration on today's infra,
then lay out what changes once IT grants **Static Web Apps + CDN**.

```mermaid
flowchart TB
    classDef done fill:#d6efe0,stroke:#3e8f6b,color:#14532d
    classDef next fill:#fff3cd,stroke:#d0a000,color:#5c4400
    classDef later fill:#e7edff,stroke:#5b76c7,color:#22307a

    subgraph now["Shipped"]
        a1["deck.gl GPU rendering"]:::done
        a2["DuckDB-on-blob serving"]:::done
        a3["browser + in-memory cache"]:::done
        a4["PMTiles + hyparquet client serving<br/>(native · buildings · admin)"]:::done
        a5["platinum tier · incremental build_platinum"]:::done
    end

    subgraph nowinfra["1 · Finish on current infra (not IT-blocked)"]
        b1["convert H3 + agreement"]:::next
        b2["self-hosted PMTiles basemap"]:::next
        b3["SAS hardening — managed identity +<br/>directory-scoped short-lived SAS"]:::next
    end

    subgraph swa["2 · After SWA + CDN access"]
        c1["SPA → Static Web Apps"]:::later
        c2["CDN / Front Door over platinum blob"]:::later
        c3["/api/token → Function (managed identity)"]:::later
        c4["retire FastAPI serving endpoints"]:::later
        c5["tighten CORS · downsize App Service"]:::later
    end

    subgraph scale["3 · Scale (data volume)"]
        d1["prod data tier (platinum + CORS on prod blob)"]:::later
        d2["gold decompose → incremental new-source"]:::later
        d3["binary / GeoArrow point transfer"]:::later
        d4["Databricks for global harmonize"]:::later
    end

    now --> nowinfra --> swa --> scale
```

**1 · Finish on current infra** — none of this needs IT. Convert the last two layers
(H3 needs `h3_cell_to_boundary` geometry-gen + its own slim values parquet; agreement
reuses the buildings tile). Self-host the basemap as PMTiles (Overture via planetiler,
or Protomaps) to drop the hosted-CARTO dependency. **Harden the SAS**: give the App
Service a managed identity (*Storage Blob Data Reader*) and have `/api/token` mint a
**directory-scoped, short-lived user-delegation SAS** to just
`projects/ds-geospatial-impact-estimates/platinum/` — the account is ADLS Gen2, so
directory scoping works. This removes the long-lived client-visible SAS *before* any
public exposure.

**2 · After SWA + CDN access** — the migration to Maxym's end-state topology, now that
the data tier (PMTiles + values in blob) is already in the right shape:
- **SPA → Static Web Apps:** move `web/dist` off the FastAPI `StaticFiles` mount to
  SWA global static hosting (edge-served, custom domain).
- **CDN / Front Door over `platinum/`:** edge-cache the PMTiles + values parquet
  (immutable, versioned via Portolan `versions.json` → long cache, bust on version);
  point the client `base_url` at the CDN. Removes per-request blob egress + latency.
- **`/api/token` → Function:** relocate the token minting into an SWA-integrated
  Azure Function using managed identity (same logic as phase 1, just hosted there).
- **Retire FastAPI serving endpoints:** once H3 + agreement are converted, the
  GeoJSON/JSON routes (`/api/native|buildings|common/*|agreement`) are dead; only
  `/api/token` (Function) + `/api/export` remain. The always-on App Service Plan can
  be **downsized or retired**.
- **Tighten CORS** from `*` to the SWA origin, set at the CDN layer.

**3 · Scale** — replicate `platinum/` + CORS to the **prod blob** so prod reads prod
(the dev/prod data split), fronted by the CDN. Decompose the monolithic gold so a new
source is incremental end-to-end. Binary/GeoArrow shrinks point transfers; Databricks
only if harmonization outgrows the single-DuckDB pipeline (global scale).

**Phasing:** finish the layers + SAS hardening now → SWA/CDN migration when access
lands → prod data tier + scale work at real/global traffic.
