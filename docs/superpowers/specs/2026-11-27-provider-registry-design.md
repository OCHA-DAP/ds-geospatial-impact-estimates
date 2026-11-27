# Damage Analysis Platform: provider registry and submission back end

**Date:** 2026-11-27
**Status:** reviewed 2026-11-27 (a colleague's review on issue #183, with the factual points
checked against Microsoft's documentation and the team's records). Decisions 1, 2, 3, 5 and 6
below are taken; 4 and the hosting choice (ADR-0045) stay open. Nothing built from it yet.
**Driver:** the form spike (branch `spike/form-auth`, PR #174) proved the provider experience:
organisation sign-up, members, emailed sign-in, the three-level submission form, records on
blob. It was built as a throwaway. This document is the design for promoting it into the
platform's provider side, structured so the pieces that depend on IT (identity provider,
database reachability, hosting plan) can be swapped in as they are granted, and so one
developer can exercise the whole system alone.

Companion decisions: [ADR-0043](../../decisions/0043-identity-seam-email-proof-now-un-idp-later.md)
(identity seam), [ADR-0044](../../decisions/0044-registry-store-and-api-runtime.md) (registry
store and API runtime), [ADR-0045](../../decisions/0045-provider-site-hosting-standard-static-web-app.md)
(where the provider site is hosted; proposed).

## Decisions

Reviewed on issue #183 on 2026-11-27. Each entry records the outcome and the reason; the
review's own wording is on the issue.

1. **What ships first.** Taken: (a). The registry goes behind a repository interface,
   implemented on blob JSON now, and membership, approvals and delivery states ship to the
   PR preview so colleagues keep grading. Rejected: (b) freezing the preview on the spike and
   building the Python API against Postgres through the laptop tunnel, which produces
   nothing visible for an unknown number of weeks. The VNet integration request for the App
   Service goes to OICT now, because it has the longest wait of all the IT dependencies.
2. **Interim API language.** Taken: Python 3.11 on the managed Functions from day one, not
   Node ported later. The review's point: everything added before a port (membership,
   approvals, sessions, audit) would be written in Node too, so the port grows for as long
   as Node stays. Microsoft's runtime table for managed Functions (page dated October 2026)
   lists `python:3.11`. The spike's handlers (about 500 lines) are rewritten in Python
   first, before any feature is added, with the pages and the URL paths unchanged. One
   finding from checking the review's open point: ocha-stratus does not fit on managed
   Functions. It installs to about 680 MB on Linux (geopandas, rasterio, pyarrow and duckdb
   are most of it) against a per-environment cap of 250 MB on Free and 500 MB on Standard.
   The interim repository therefore uses `azure-storage-blob` directly (about 50 MB with
   the Postgres driver included), and ocha-stratus arrives with the App Service target,
   behind the same interface. ADR-0044.
3. **Approval model.** Taken, with three changes from the review and from the discussion on
   the artifact. An organisation is `pending` until a staff member approves it. There are no
   invitations: a person registers by picking their organisation from the list of registered
   ones (a new organisation is added only when nothing fits, and then joins the list for the
   next person), which creates a join request that an admin of the organisation or a staff
   member approves. The first member of a new organisation is its admin. "One address, one
   organisation" is a registry rule, enforced in code and relaxable later for people who
   work with two organisations. Because staff approval is what stops someone registering a
   known organisation's name first, the review screen shows what the reviewer needs to
   check the person's link to it: the address domain, the organisation's website, and the
   registered organisations with similar names. *Assumed, to confirm:* a join request needs
   approval; picking from the list alone is not enough, since with self-service sign-up
   anyone could otherwise submit as any listed organisation.
4. **Sign-in option A or B.** Open. The review's advice: request both and decide when OICT
   has answered, and test guests first, because guests are in the approved architecture and
   a test registration with guests in the audience was requested on 25 November for the
   submission test site, while B2C would change the approved architecture and needs the
   task force's second approval. The approved architecture names the UN's Entra ID as the
   only user sign-in, so the emailed link cannot be the production sign-in under either
   option. One difference between the options that this design must absorb: every app
   registration comes with an Entra security group, and OICT's proposals for the team's
   other sites set *assignment required*, so under A a person whom staff approve in the
   registry still cannot sign in until a registration owner adds them to the group. Under A
   the group gates sign-in and the registry decides what a signed-in person may do; under B
   the registry does both. Question back to the review: will the submission test
   registration be assignment-required? Nobody has read the pre-approved domain list yet;
   if the main partners are on it, staff can invite them directly.
5. **When the interim reaches the production host.** Taken: the emailed-link sign-in stays
   on a preview with test data, and the provider side merges to the production host only
   once the UN sign-in is in place. Until then `STORE=prod` raises. The dev credentials
   baked into the bundle are half the reason; the approved architecture's Entra-only
   sign-in is the other half. The config seam still moves to Static Web App application
   settings before that merge (a Contributor can set them and the PIM-eligible role
   covers it); `STORE=prod` then means a `registry-prod/` prefix with its own scoped
   credential, mirroring the viewer's staging and prod data split.
6. **Membership in Listmonk lists (option C on the artifact).** Rejected. Membership stays
   in the registry, and Listmonk lists become a one-way copy of it, used for notifications
   only. Reasons: authorisation lives in the registry by this design's own rule; our
   Listmonk sets the one-click unsubscribe header on every message (`privacy.unsubscribe_header`
   is on, read from its settings on 27 November), so a member or their mail client could
   remove their own access, which has already happened to a group address on an alert list;
   sign-in would stop whenever Listmonk is down, as it was for three days in September
   2026; and the API would need a subscriber-managing Listmonk credential inside a
   public-facing service.

## Constraints (facts, checked 2026-11-25 to 27)

- **Postgres is private-endpoint only** since 2026-09-30. Reachable from Databricks, from a
  laptop through the Databricks SSH tunnel, and from App Services that OICT has
  VNet-integrated. Not reachable from Static Web App managed Functions (no VNet path) nor
  from our App Service fallback `chd-ds-geospatial-impact-viewer` (not integrated). Some team
  App Services are integrated, so it is a request with precedent, not a new capability.
- **The viewer's Static Web App is on the Free plan.** Free allows only Microsoft's
  preconfigured sign-in providers and no linked backend. A custom provider (UN tenant or UN
  B2C) and a linked App Service both need Standard. Custom domains: two on Free, six on
  Standard. A Standard Static Web App for the submission side already exists, created by
  OCHA's technical support on 26 November with a hostname under unocha.org attached and a
  placeholder deployed from another repository; whether the provider side deploys there or
  the viewer's app is upgraded is ADR-0045.
- **UN sign-in waits on app registrations, not on the architecture review.** The platform's
  architecture review was approved on 23 November 2026. (The first draft of this document
  and of ADR-0043 said it was still pending; that was wrong.) Test registrations were
  requested on 25 November, one of them for the submission test site with guests in the
  audience. A production registration needs OICT Cybersecurity's assessment of a working
  non-production site and the task force's second approval. The UN tenant refuses consent
  to Microsoft's shared Static Web Apps registration (seen 25 Nov: "Need admin approval"),
  so the built-in provider is unusable for UN accounts.
- **Managed Functions limits** (Microsoft's documentation, read 27 Nov). Requests are cut
  off at 45 seconds, and Python on the Consumption plan cold-starts in a few seconds on top.
  Triggers are HTTP only; no managed identity and no Key Vault references. A linked backend
  and a custom domain apply to the production environment only: neither works on
  pull-request previews, so review by preview ends once the App Service is the backend, and
  links emailed from previews keep the generated hostname. Storage per environment is
  250 MB on Free and 500 MB on Standard, which is what keeps ocha-stratus out of the interim.
- **No file uploads, ever.** Providers submit links; the platform fetches and validates.
  Fetching provider-controlled bytes is isolated (size cap, type check, timeout).
- **A sign-in action emails exactly one address**, the one typed. Asserted by a test.
- **Emailed links need a hostname the team controls.** Links built from a generic cloud
  hostname were flagged by Safe Browsing. Hostname under datascience.unocha.org (DNS record
  from OCHA's technical support, zone `imb-dns`, read-only to us).
- **Mail run modes follow the team convention** (KB `infrastructure/email-testing.md`):
  unset means safe; only explicit production config sends real mail.

## Target architecture and the interim

| Part | Interim (buildable now) | Target (after IT grants) | What changes |
|---|---|---|---|
| Front end | Static Web App, Free, generated hostname | Same app, Standard, `<name>.datascience.unocha.org` | Plan and DNS only |
| API | Python 3.11 managed Functions (HTTP only), `azure-storage-blob` directly | The same Python code on the App Service in the shared plan, VNet-integrated, linked as the SWA backend so `/api` stays same-origin, with ocha-stratus and Postgres behind the repository interface | Host and repository implementation; no port; URL paths unchanged |
| Identity proof | Emailed single-use link, our session cookie | UN identity provider through the SWA custom provider; SWA session | The code behind one function (ADR-0043) |
| Registry | Blob JSON repository with ETag concurrency, dev account | Postgres, team server, by private IP | Repository implementation (ADR-0044) |
| Delivery files | Fetched into bronze on blob | Same | Nothing |
| Mail | Listmonk transactional endpoint, one recipient | Same | Nothing |
| Configuration | `secrets.json` written by the deploy workflow (dev credentials only) | App settings or Key Vault references | One config module |

Standalone Function apps were considered and rejected: the Consumption plan has no VNet path,
and the plans that do cost money and are their own resource request.

## Seams

Every seam is one module with one interface. Nothing outside the module knows which
implementation is behind it.

| Seam | Interface | Interim | Target |
|---|---|---|---|
| `principal` | `principal(request) -> {user_id, email, verified_by, verified_at} \| null` | Reads our session cookie, looks up the session row | Reads the client principal header the Static Web App adds after UN sign-in |
| `registry` | Repository: organisations, members, join requests, products, deliveries, sessions, link tokens, audit | Blob JSON, one object per record plus small indexes, `If-Match` on every write | Postgres tables, transactions |
| `mail` | `send(to, subject, html)`, exactly one `to` | Listmonk `/tx` | Same |
| `config` | `secret(name)`, fails loudly when missing | `secrets.json` from the workflow | App settings / Key Vault |
| `fetcher` | `fetch_validated(url, limits) -> file + facts` | Same code, run inside the Function | Isolated worker |

Rules that make the seams real:

- Records key on our own user id. An identity (email proof, later a UN object id) is a
  linked row under that user. Changing identity provider adds a row, never migrates records.
- Authorization (membership, roles, organisation state) lives in the registry. UN groups and
  app roles are never consulted for what a signed-in person may do. Under sign-in option A
  an Entra security group additionally gates who can sign in at all (decision 4); that is a
  property of the provider, not a second source of roles.
- "Identity verified" is one event in the state machine, whatever produced it.
- The parts that die when the provider changes are in one folder: link issue and redeem,
  cookie minting, the one mail that carries a link.

## Domain model and states

Entities: `user`, `identity` (per user, per provider), `organisation`, `membership`
(user, organisation, role `admin`/`member`), `join_request`, `product` (a provider's product
definition: columns, geometry mode, damage mapping, extent mode), `delivery` (one product
version for one event: links, dates, headline numbers), `session`, `link_token` (single use),
`audit` (who did what, when), `outbox` (mail captured in test modes).

States:

- organisation: `pending` → `approved` → `suspended`. Only `approved` organisations submit.
- membership: `active` → `removed`. Created only by an accepted join request (or by the
  organisation's registration, for its first member). Removal ends the member's sessions.
- join request: `open` → `accepted` | `declined`. Accepted by an admin of the organisation
  or by staff.
- delivery: `submitted` → `validated` | `rejected` → `published`. Validation fetches the two
  links (product, analysed extent) and records the facts it read. A late extent is an edit of
  the delivery, not a new one.

One address belongs to one organisation: a registry rule, enforced in code, relaxable later.
An organisation has at least one admin. Organisation names are checked for near-duplicates
twice: the picker flags likely matches as the person types, and the staff review of a new
organisation lists the registered ones with similar names.

## Run modes and the one-developer sandbox

- `MAIL_MODE`: `capture` (default; mail goes to the outbox table, nothing sent), `redirect`
  (every message to `MAIL_REDIRECT_TO` with the intended recipient in the subject, subject
  prefixed `[TEST]`), `real`. Unset or malformed is `capture`; a bad value raises.
- `STORE`: `local` (Azurite blob emulator, later a local Postgres), `dev`, `prod`. Unset is
  `local`. The PR preview runs `STORE=dev` with `MAIL_MODE=real` (colleagues must receive
  their links; subjects carry `[TEST]` while the store is not `prod`); production sets `prod`
  and `real` explicitly in the workflow. The outbox page is served only when `STORE=local`,
  so a single-use link is never readable from a deployed URL.
- `scripts/reset` drops the store for the selected tier (never `prod`) and loads fixtures:
  three organisations in each state, members in each role, deliveries in each state.
- A dev-only page lists the outbox so emailed links can be clicked without email.
- Identities: plus addressing (`name+orgA@un.org`) gives distinct addresses in one inbox.
  To verify with one send before relying on it.
- Being several people: browser profiles for manual play; the puppeteer scripts drive
  multi-actor flows (a partner registers, a staff member approves, a colleague joins).
- The UN sign-in path without OICT: the Static Web Apps CLI (`swa start`) emulates the
  built-in auth with a local login page where a name, provider and roles are typed. The
  target `principal` implementation is tested against it on the laptop.

## Carried forward from the security review (2026-11-20)

Sessions become rows and are revocable on logout and removal (O3). Emailed links are single
use and redeemed by a POST from a landing page so mail scanners do not burn them (O4).
Listings are scoped to the caller's organisation; staff see all (O5). Throttles live in the
registry, per address and per source address (O7). Clients get generic error text; detail
goes to logs (O8). Logout is a POST. Secrets are dev-tier only until the config seam moves
to app settings (O1, O2).

## IT dependencies and what each unlocks

| Request | To whom | Unlocks |
|---|---|---|
| DNS record `<name>.datascience.unocha.org` → the app | OCHA technical support | Clean hostname; stable redirect URI for the app registration |
| A Standard Static Web App for the provider site | Either the existing Standard test app (the team's), or upgrading the viewer's app ourselves via PIM Contributor (about USD 9/month) | Custom sign-in provider; linked backend; six domains. ADR-0045 |
| VNet integration of the App Service | OICT (to request now) | Python API reaching Postgres; the registry target |
| Architecture review | Approved 23 November 2026 | App registrations (requested); the production registration also needs the security assessment and the second approval |
| App registration (option A requested 25 November for the test site; B not requested) | OICT via Unite | UN sign-in through the custom provider: test first, production after the assessment |

Nothing in the interim column waits on any of these.

## From the spike: keep, port, delete

Keep: the pages in `web/public/form-spike/` (renamed out of "spike"), the form logic and
validation, the single-recipient test, the puppeteer flows, the Listmonk relay pattern.
Rewrite: the Function handlers in Python 3.11, into the seams above, before any feature is
added; the same code later moves to the App Service.
Replace: the blob layout (`_organisations/`, `_contacts/`) with the repository's layout;
self-service registration with the approval model. Delete when the target lands: link issue
and redeem, the cookie code, `secrets.json`.

## Calls made after the builder check

A reviewer read the draft as the person who would build it. These are my answers; each is a
default that can be overturned in review.

- **Staff.** Staff are members of one internal organisation flagged `is_staff` (OCHA CHD
  Data Science). It is created by the fixtures and by a one-off bootstrap in production that
  reads `STAFF_EMAILS` from configuration on first sign-in; after that, staff add staff like
  any admin adds members. Approve and reject are web actions by a signed-in staff member, not
  scripts. The `principal` carries no role; roles come from membership lookups in the
  registry. In the target, staff identity can additionally be asserted by the UN account
  domain, but the registry membership stays the authority.
- **Admin versus member.** Admins accept join requests, remove members and edit the
  organisation; members submit and edit their own deliveries. There is no invite action
  anywhere. The last admin cannot be removed.
- **Validation in the interim is HTTP-level.** On submit, the Function fetches each link
  with a size cap and timeout and records status, content type, size, checksum and the facts
  the browser-side reader reported. Parsing provider files on the server is the target's
  isolated worker, not the interim. Keeps the port small and O9 out of the interim.
- **Validation runs synchronously on submit, inside the 45 second limit.** No queue in the
  interim. The two link fetches run in parallel with a short per-fetch timeout (the
  builder's call, well under half the limit so cold start fits too). A fetch that times out
  leaves the delivery `submitted` with the validation recorded as `timed_out`, visible to
  the submitter and to staff, who can re-run it. `published` is set by
  a staff action once the product is in the viewer; wiring the registry to the harmonise and
  promote pipeline is future work, noted under out of scope. A late extent edit returns the
  delivery to `submitted` and revalidates.
- **Products are versioned.** A delivery pins a product version. Editing a product definition
  creates a new version; earlier deliveries keep theirs. The form stays one page, pre-filled
  from the latest version.

## Out of scope

Choosing the platform name. The viewer itself (stays public). Raster validation beyond
recording the links. Staff review tooling beyond approve and reject. Retiring the App
Service fallback (it becomes the API host instead).

## Left to the builder

Blob object layout and index shape for the interim repository; the exact validation facts
recorded per delivery; fixture content; the dev outbox page's look; test structure.

## Where the sign-in research lives

The comparison of the spike with the UN sign-in options, with diagrams, is the artifact
"Spike versus Entra" (https://claude.ai/artifact/MmdWkEAgDv8XppNC4FqCwd?sk=RrwZ-rC34nypLeDMstCEfA, shared with the OCHA
Centre organisation on claude.ai). The catalogue research it rests on is kept out of this
public repository on purpose; it lives beside the artifact source in the maintainer's clone
(`docs/provider-sign-in/`, excluded from git) and can be shared on request.
