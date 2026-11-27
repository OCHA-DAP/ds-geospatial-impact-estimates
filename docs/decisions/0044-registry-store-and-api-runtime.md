---
status: "accepted"
date: 2026-11-27
deciders: Zack Arno
consulted: Tristan Downing (review on issue #183)
---

# Registry store and API runtime: blob repository on Python managed Functions now, Postgres on a VNet-integrated App Service later

## Context and Problem Statement

The provider registry (organisations, members, approvals, deliveries, sessions, audit) wants a
relational store with transactions. The team's Postgres is the convention. Since 2026-09-30
it is reachable only over private endpoints: from Databricks, from a laptop through the
Databricks SSH tunnel, and from App Services OICT has VNet-integrated. Neither runtime we can
deploy to today reaches it: Static Web App managed Functions have no VNet path, and the
project's App Service fallback is not integrated. The spike's API is Node, written for speed.
Where does the registry live, where does the API run, and in which language, now and later?

## Decision Drivers

* Reachability from the runtime that serves `/api`, today.
* Team conventions: Postgres through ocha-stratus, Python.
* One language across the back end and the team's pipelines, and no port later.
* Same-origin `/api` for the front end (cookies, no CORS).
* Tiny volumes: tens of organisations, hundreds of deliveries.
* Managed Functions limits (Microsoft's documentation, read 2026-11-27): HTTP triggers only,
  45 second requests, 250 MB per environment on Free and 500 MB on Standard, runtimes
  `python:3.9` to `python:3.11` and `node:20` to `node:22`.

## Considered Options

* Blob JSON repository (ETag concurrency) behind an interface, on Python 3.11 managed
  Functions now; the same code on a VNet-integrated App Service with Postgres later.
* The same, but keeping the spike's Node handlers as the interim and porting to Python with
  the move (this record's first draft).
* Postgres now from the managed Functions. Not possible: no network path.
* Azure Table storage on the team storage account (reachable, atomic per entity).
* A standalone Function app with VNet integration (Premium or Flex plan).
* Listmonk lists as the membership store, with the registry holding everything else
  (the pattern the storm alerts use for subscriptions).

## Decision Outcome

Chosen option: the blob repository on Python managed Functions now, with the Postgres App
Service as the target. The repository interface is the seam; volumes are small enough that one
object per record plus small indexes is adequate, and the dev storage account is reachable
from every runtime, including a laptop and the Azurite emulator. The spike's Node handlers
(about 500 lines) are rewritten in Python before any feature is added, with the pages and URL
paths unchanged. The target is the same Python code on the App Service, linked as the Static
Web App's backend (needs Standard: ADR-0043) and VNet-integrated by OICT, with precedent in the
team's other apps.

One constraint found while checking the review's open point: ocha-stratus does not fit on
managed Functions. Installed for Linux x86-64 it is about 680 MB (geopandas, rasterio, pyarrow
and duckdb are most of it), against the 250 MB or 500 MB cap. The interim repository uses
`azure-storage-blob` directly (about 50 MB with the Postgres driver included); ocha-stratus
arrives with the App Service, behind the same interface. The interface therefore hides the
library as well as the store.

### Consequences

* Good, because features ship to the preview now with no IT dependency.
* Good, because there is one back-end language from the start and nothing to port.
* Good, because the target follows every team convention for database access.
* Bad, because the rewrite of the spike's handlers is a few days with no visible change.
* Bad, because the interim cannot use ocha-stratus; the blob client is written once by hand.
* Bad, because blob offers no cross-record transactions; the repository must keep invariants
  (one address, one organisation) by construction and by ETag checks.

## Pros and Cons of the Options

### Node interim, Python port later
* Good, because the spike runs today and nothing is rewritten before features ship.
* Bad, because membership, approvals, sessions and audit would all be added in Node before
  the port, so the port grows for as long as Node stays (the review's point).
* Bad, because the team's pipelines and the target API are Python; two languages for the
  life of the interim.

### Azure Table storage
* Good, because it is reachable now and gives entity-level atomicity and queries.
* Bad, because it adds a third storage API to the team's set for no lasting benefit; it
  would be replaced by Postgres as surely as blob JSON.

### Standalone VNet-integrated Function app
* Good, because it could reach Postgres and keep Node or Python.
* Bad, because the plans with VNet integration cost money and the app is its own resource
  request; the App Service in the shared plan already exists.

### Listmonk lists as the membership store
* Good, because the pattern exists (one list per country for the storm alerts), the lists
  are already a Postgres-backed, IT-approved system, and notifications would need the lists
  anyway.
* Bad, because authorisation would leave the registry, against the design's own rule.
* Bad, because our Listmonk sets the one-click unsubscribe header on every message
  (`privacy.unsubscribe_header` on, read 2026-11-27), so a member or their mail client could
  remove their own access; this has happened to a group address on an alert list.
* Bad, because sign-in would stop whenever Listmonk is down, as it was for three days in
  September 2026.
* Bad, because the API would need a subscriber-managing Listmonk credential inside a
  public-facing service.

Lists stay as a one-way copy of membership, used for notifications only.

## More Information

KB `infrastructure/database.md` and the internal `db-network-access.md` list which runtimes
reach the servers and which App Services are integrated. Runtime versions and limits:
Microsoft Learn, *Supported languages and runtimes in Azure Static Web Apps* (dated
2026-10-05) and *Quotas in Azure Static Web Apps*. Sizes measured with `uv pip install
--python-platform x86_64-manylinux_2_28 --only-binary :all:` on 2026-11-27. Revisit when VNet
integration is granted; the move and the data migration are the plan's final steps.
