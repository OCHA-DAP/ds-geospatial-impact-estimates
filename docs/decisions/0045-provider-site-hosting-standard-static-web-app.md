---
status: "proposed"
date: 2026-11-27
deciders: Zack Arno
consulted: Tristan Downing (review on issue #183)
---

# Where the provider site is hosted: a Standard Static Web App

If the viewer's own app is upgraded (option 1 below), this supersedes the hosting-plan part
of ADR-0023, which chose Free. If the provider side gets its own app (option 2), ADR-0023
stands and the viewer stays on Free.

## Context and Problem Statement

ADR-0023 put the viewer on a Free Static Web App beside the App Service. The provider side
needs two things Free does not offer: a custom sign-in provider (the UN tenant or the UN B2C
tenant; Free allows only Microsoft's preconfigured providers, which the UN tenant refuses
consent to) and a linked backend so the API on the App Service is served same-origin under
`/api`. Standard also raises custom domains from two to six. The first draft of this record
assumed the viewer's app would be upgraded. The review on issue #183 pointed out that a
Standard Static Web App for the submission side already exists: created by OCHA's technical
support on 26 November as part of the team's site consolidation, with a hostname under
unocha.org attached, a placeholder deployed from another repository's `main`, and a test app
registration (with guests in the audience) requested on 25 November.

## Decision Drivers

* Both UN sign-in options require Standard (Microsoft: custom authentication is Standard only).
* The target API runs on the App Service and must be same-origin.
* The public viewer has no need of Standard; the provider side does.
* An existing hostname and registration avoid two requests.
* Cost: about USD 9 per month per Standard app.

## Considered Options

1. Upgrade the viewer's app to Standard and host the provider side on it, under one hostname.
2. Host the provider side on the existing Standard submission app, leaving the viewer on Free.
3. Stay on Free; serve the API cross-origin from the App Service with CORS and cross-site cookies.

## Decision Outcome

Proposed: option 2. The hostname, the plan and the registration already exist for it, and the
viewer keeps its Free plan and its own deploy. Not yet taken because it changes an app another
team member manages: its deployment source moves from the placeholder repository to this one,
and its registration's reply URLs are set for it. To confirm with the review before acting.

### Consequences

* Good, because UN sign-in and the linked backend become configuration, not architecture.
* Good, because the viewer and the provider site deploy and scale separately.
* Bad, because two apps mean two deploy workflows and two sets of settings to keep aligned.
* Bad, because links between the viewer and the provider site cross hostnames (no shared
  cookie, which the design does not need).

## Pros and Cons of the Options

### Upgrade the viewer's app
* Good, because one app, one hostname, one workflow.
* Bad, because it needs a second hostname request and a second registration for the same
  purpose as the ones that exist, and puts the public viewer on a paid plan for nothing it uses.

### Stay on Free with a cross-origin API
* Good, because no cost.
* Bad, because cross-site cookies (`SameSite=None`) weaken the session model, every
  endpoint needs CORS, and UN sign-in is still impossible.

## More Information

sign-in research 2026-11-25; design `docs/superpowers/specs/2026-11-27-provider-registry-design.md`
(decision 4 and the IT dependencies table); review on issue #183.
