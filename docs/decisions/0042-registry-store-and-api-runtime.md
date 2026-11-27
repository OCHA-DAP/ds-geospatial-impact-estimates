---
status: "proposed"
date: 2026-11-27
deciders: Zack Arno
---

# Registry store and API runtime: blob repository on managed Functions now, Postgres on a VNet-integrated App Service later

## Context and Problem Statement

The provider registry (organisations, members, approvals, deliveries, sessions, audit) wants a
relational store with transactions. The team's Postgres is the convention. Since 2026-09-30
it is reachable only over private endpoints: from Databricks, from a laptop through the
Databricks SSH tunnel, and from App Services OICT has VNet-integrated. Neither runtime we can
deploy to today reaches it: Static Web App managed Functions have no VNet path, and the
project's App Service fallback is not integrated. Where does the registry live, and where
does the API run, now and later?

## Decision Drivers

* Reachability from the runtime that serves `/api`, today.
* Team conventions: Postgres through ocha-stratus, Python.
* Same-origin `/api` for the front end (cookies, no CORS).
* Tiny volumes: tens of organisations, hundreds of deliveries.

## Considered Options

* Blob JSON repository (ETag concurrency) behind an interface on the managed Functions now;
  Postgres on a VNet-integrated App Service linked to the Static Web App later.
* Postgres now from the managed Functions. Not possible: no network path.
* Azure Table storage on the team storage account (reachable, atomic per entity).
* A standalone Function app with VNet integration (Premium or Flex plan).

## Decision Outcome

Chosen option: the blob repository now with the Postgres App Service as the target. The
repository interface is the seam; volumes are small enough that one object per record plus
small indexes is adequate, and the dev storage account is reachable from every runtime,
including a laptop and the Azurite emulator. The target API is Python with ocha-stratus,
linked as the Static Web App's backend (needs Standard: ADR-0043) and VNet-integrated by
OICT, with precedent in the team's other apps.

### Consequences

* Good, because features ship to the preview now with no IT dependency.
* Good, because the target follows every team convention for database access.
* Bad, because the interim Node handlers (about 500 lines) are ported to Python later.
* Bad, because blob offers no cross-record transactions; the repository must keep invariants
  (one address, one organisation) by construction and by ETag checks.

## Pros and Cons of the Options

### Azure Table storage
* Good, because it is reachable now and gives entity-level atomicity and queries.
* Bad, because it adds a third storage API to the team's set for no lasting benefit; it
  would be replaced by Postgres as surely as blob JSON.

### Standalone VNet-integrated Function app
* Good, because it could reach Postgres and keep Node or Python.
* Bad, because the plans with VNet integration cost money and the app is its own resource
  request; the App Service in the shared plan already exists.

## More Information

KB `infrastructure/database.md` and the internal `db-network-access.md` list which runtimes
reach the servers and which App Services are integrated. Revisit when VNet integration is
granted; the port and the data migration are the plan's final steps.
