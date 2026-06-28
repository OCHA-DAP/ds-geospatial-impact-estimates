# Roadmap — speed, scale & slickness

Where the [current stack](architecture.md) can go as audience and data volume
grow. Phased so each step is cheap relative to its payoff; nothing here is built
yet beyond what's marked *shipped*. (This is the working source for a future
ADR-0008.)

```mermaid
flowchart TB
    classDef done fill:#d6efe0,stroke:#3e8f6b,color:#14532d
    classDef next fill:#fff3cd,stroke:#d0a000,color:#5c4400
    classDef later fill:#e7edff,stroke:#5b76c7,color:#22307a

    subgraph now["Shipped"]
        a1["deck.gl GPU rendering"]:::done
        a2["DuckDB-on-blob serving"]:::done
        a3["browser + in-memory cache"]:::done
    end

    subgraph speed["1 · Speed (cheap, high impact)"]
        b1["CDN / Front Door —<br/>cache API + static"]:::next
        b2["precompute serving artifacts"]:::next
    end

    subgraph scale["2 · Scalability (data volume)"]
        c1["PMTiles · buildings + H3"]:::later
        c2["geometry tiles +<br/>attribute-JSON split"]:::later
        c3["binary / GeoArrow transfer"]:::later
        c4["Databricks for global harmonize"]:::later
    end

    subgraph slick["3 · Slickness (UX & breadth)"]
        d1["scatter + linked brushing"]:::later
        d2["raster (SAR) damage source"]:::later
        d3["managed identity + OIDC"]:::later
    end

    now --> speed --> scale --> slick
```

**1 · Speed** — mostly config, no data-model change. A CDN (Azure Front Door) in
front caches the deterministic, read-only API + static SPA: cold ~15 s → instant
for everyone, and the app stops absorbing concurrency. Precomputing serving
artifacts pulls DuckDB off the hot path.

**2 · Scalability** — the data-volume answer. PMTiles (`tippecanoe` → blob, range
requests, no tile server) so the client only fetches tiles in view; splitting
static geometry tiles from a tiny dynamic attribute payload keeps per-source/
per-metric styling instant; binary/GeoArrow shrinks point transfers. Databricks
only if harmonization outgrows the single-DuckDB pipeline (e.g. global scale).

**3 · Slickness** — linked scatter/brushing for source comparison, the raster
(SAR) damage source, and the managed-identity/OIDC auth upgrade (removes the
stored SAS / publish-profile secrets).

**Phasing:** CDN now (soft launch) → PMTiles + geometry/attribute split when data
grows past a single city → binary + Front Door tuning at real/global traffic.
