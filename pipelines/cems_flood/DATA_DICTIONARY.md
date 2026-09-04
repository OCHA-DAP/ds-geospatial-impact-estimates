# CEMS flood corpus: data dictionary

Every column in the silver tables, split into **ours** (defined by this
pipeline) and **CEMS-native** (passed through; definitions from the official
*Manual for CEMS Rapid Mapping Products*, JRC121741, 2020). The manual and
the official data-model diagrams are archived beside the data at
`global/copernicus_ems/flood/bronze/_meta/docs/` (upstream loses documents
too). Full value domains: manual Annex 6 (event types), Annex 4 (detection
methods). Bronze ledger columns are documented in
[`ACQUISITION.md`](ACQUISITION.md); pipeline behavior in
[`README.md`](README.md).

## silver/observed_event (one row per flood polygon)

### Ours

| column | meaning |
|---|---|
| `code` | activation, `EMSRnnn` |
| `target_id` | bronze zip this row came from: `{code}/{zip basename}` |
| `product_class` | DEL / FEP / GRA (see product types below) |
| `aoi` | area of interest, `AOInn Name` as the portal labels it |
| `layer_kind` | `observed` (the flood extent) or a supplementary layer: `modelled`, `max_extent`, `flood_depth` (2025+ DEL products) |
| `layer_name` | source shapefile basename, verbatim |
| `acq_datetime` | imagery acquisition time (UTC, naive) when known |
| `acq_window_start` / `acq_window_end` | bounds when only an interval is known |
| `acq_precision` | how tight the above is: `minute` \| `date` \| `window` |
| `acq_method` | how we know: `attribute` (2012-16 per-feature dates) \| `source_table` (2017+ in-package source DBF joined via `dmg_src_id`) \| `api` / `api_window` (2023+ portal API) \| `window` (last resort: event→publish bounds; start is a soft bound) |
| `delivery_time` | product delivery per the harvest ledger |
| `attrs_json` | ALL raw source attributes as verbatim JSON, so era mapping mistakes are never destructive |
| `geometry` | polygon, EPSG:4326 |

### CEMS-native (manual §4.2, quoted/condensed)

| column | CEMS definition |
|---|---|
| `event_type` | "type of crisis or disaster event", adjusted EM-DAT classification (e.g. `5-Flood`); full domain in Annex 6. Older eras carry variants (`EM009 - Flood`, numeric codes; `998`/`999` = not applicable/unknown), normalized best-effort with the raw kept in `attrs_json` |
| `obj_desc` | "subtype of crisis or disaster event" (e.g. `Riverine flood`, `Flash flood`) |
| `det_method` | "methodology used to extract or derive the spatial information": photo-interpretation, semi-automatic extraction, automatic extraction, modelling (Annex 4) |
| `notation` | "any complementary information related to the dataset" (free text) |
| `dmg_src_id` | "foreign key … to the primary key (`src_id`) of the SOURCE table. It indicates the data source used to extract the damage information", i.e. which image this polygon was digitized from |

Note: CEMS's raw `area` attribute (in `attrs_json`) is in **hectares** per the
manual; compute areas from the geometry (as gold does, in km²) rather than
trusting it across eras.

## silver/sources (one row per product × source image)

CEMS SOURCE table (manual §4.2.1: "metadata information related to the
imagery and other data sources used for the analysis"), plus API images.

| column | CEMS definition / origin |
|---|---|
| `src_id` | primary key; `dmg_src_id` on polygons points here |
| `source_nam` | "the imagery mission name or the vector data source" (e.g. `COSMO-SkyMed`; `Open Street Map` rows are basemap sources, ids ≥ 900) |
| `src_date` | "date of image acquisition … dd/mm/yyyy" |
| `source_tm` | "time of image acquisition … Thh:mm:ssZ UTC"; absent for vector sources |
| `sensor_gsd` | "spatial resolution of the image pixels in meters" |
| `eventphase` | "timeliness of the image acquisition compared to the event": `Pre-event` / `Post-event` |
| `method` (ours) | `package` (from the in-zip source DBF) or `api` (portal images endpoint, 2023+, includes `sensorType` and exact `acquisitionTime`) |

## silver/coverage (what was actually observed)

| column | meaning |
|---|---|
| `role` (ours) | `aoi` (analysed area of interest) \| `footprint` (image footprint / sensor metadata) \| `not_analysed` (clouds, no data, void) |
| `or_src_id` | CEMS: original source id of the footprint (joins `sources.src_id`) |
| `attrs_json`, `geometry`, keys | as in observed_event |

Interpretation rule: a location is a valid negative ("observed, not flooded")
only inside `footprint − not_analysed`. Outside that, absence of a flood
polygon means *unobserved*, not dry.

## Product types (`product_class`)

A "product" is one analysis of one area of interest, delivered as printable
maps plus the vector package we archive. The manual (p. 8) defines four
types, "one pre-event (reference) and three post-event (first estimate,
delineation, grading)":

| code | name | what it answers | speed / depth |
|---|---|---|---|
| REF | Reference | what the area looked like before the event | pre-event baseline. Not fetched by this pipeline (rows are kept in the bronze ledger as `excluded_ref`) |
| FEP | First Estimate | "where is it worst?" | fastest, deliberately rough |
| DEL | Delineation | how far does the flood extend? | the standard flood-extent product |
| GRA | Grading | how badly is each asset damaged? | slowest, includes the extent plus per-asset damage grades |

Two suffixes appear in file names (and so in `target_id`), defined on p. 9
of the manual:

- **`MONITnn`** means the product is a *monitoring update*: the same AOI
  re-analysed later with new imagery. `MONIT01` is the first update,
  `MONIT02` the second, and so on; the original analysis carries `PRODUCT`
  instead. For floods this is how the rise and recession of water shows up
  as a time series.
- **`vN`** is a re-delivery of the same analysis (a correction). `v2`
  supersedes `v1`; both are archived.

**Interpretation caveat for monitoring floods** (manual §3.2.9): in some
monitoring products the reported affected area "cumulates all affected area
extents from previous post-event products" (a disclaimer note on the map
says so). So a monitoring extent is not guaranteed to be a same-day
snapshot; where the distinction matters, compare geometries across the
series (a shrinking area, as in EMSR871 AOI01, proves a snapshot) or check
the archived map PDF's disclaimer.

## Era mapping (raw → canonical)

| era | extent layer | event type from | acquisition from |
|---|---|---|---|
| 2012-13 | `*Crisis_event_A` / `*Event_A_M` | `SBTYPdes` | per-feature `SRC_DATE` |
| 2014-16 | `*crisis_information_poly` | `subtype` | per-feature `src_date` (+ time in `src_info`) |
| 2017-18 | `*observed_event_a` | `event_type` | source DBF via `dmg_src_id` |
| 2019-23 | `*observedEventA_r1_v*` | `event_type` | source DBF via `dmg_src_id` |
| 2023+ | `*observedEventA_v*` | `event_type` | source DBF; portal API as fallback |
