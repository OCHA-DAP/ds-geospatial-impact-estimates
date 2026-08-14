# Multi-Event Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the data lake and viewer multi-event (event-keyed partitions, event registry, landing page + per-event routes), migrate the Venezuela data under `event=20260624-ve-earthquake`, and onboard the Colombia earthquake — without breaking either live host.

**Architecture:** An `events.yaml` registry in the repo is the sole authority for events; `event=` becomes the first partition segment under each blob tier via one choke point (`gie.config.blob_path`), with `event=None` as the *explicit* opt-out for shared reference data and the legacy-pinned App Service. The existing VE tree is server-side–copied (never moved) under its event; the SPA gains hash routes (`#/e/<event_id>`) and a landing page, reading `events.json` from platinum through the unchanged token issuer.

**Tech Stack:** Python 3.13 (uv-managed venv), DuckDB-over-blob, Azure Data Lake/Blob SDK, PyYAML, pytest; Vite + TypeScript SPA (MapLibre GL, PMTiles, hyparquet); GitHub Actions → Azure SWA.

**Spec:** `docs/superpowers/specs/2026-08-14-multi-event-foundation-design.md`

## Global Constraints

- Run Python via `uv run` (bare `python` fails — pyenv pin not installed). ETL scripts need `uv run --group etl python ...`; tests are `uv run pytest`.
- Never include Co-Authored-By lines or any Claude/AI attribution in commits.
- Fail loudly (project rule): no silent fallbacks, no broad `except ... continue`; absence vs failure must be distinguishable; degradation is opt-in via explicit parameters.
- VE event ID is exactly `20260624-ve-earthquake` (M7.5 onset 2026-06-24 UTC). Colombia's ID is fixed from the USGS onset date at registration (Task 9).
- The event_id slug is a **mnemonic, never parsed** — the registry fields are authoritative.
- Trunk is `v1` (NOT `main` — `main` is empty). `swa-deploy.yml` deploys SWA **prod** on every push to `v1` touching `web/**`; therefore ALL `web/**` changes go on a feature branch + PR (PRs get an SWA preview env on staging data). Data-side changes (`src/`, `pipelines/`, `scripts/`, docs) may commit to `v1` directly.
- The App Service (classic host) stays pinned to the **legacy un-evented layout**: `src/gie/serving.py` and `api/` must keep resolving legacy paths (`event=None`). Do not event-scope them.
- Spec deviation, agreed rationale: the spec's "`--event` flag on every pipeline" materializes as (a) the **required keyword-only `event` argument** at the config choke point — universal, no default, TypeError if omitted — plus (b) validated `EVENT` constants in the single-event VE scripts (each is already single-event by construction: hardcoded activation codes, AOIs), plus (c) real CLI flags on genuinely multi-event scripts (`ingest_codab`). Same fail-loudly guarantee, less ceremony.

---

### Task 1: Sever the SWA → App Service export fallback

The live SWA bundle's only App Service reference is the XLSX-export *failure* fallback. Remove it: stop setting `VITE_API_BASE` in the SWA deploy, and make client-export failure surface an error instead of navigating to an empty href. The classic App Service build (which never sets `VITE_API_BASE` and falls back to same-origin `""` → its own `/api/export.xlsx`) is byte-identically unchanged in behavior.

**Files:**
- Modify: `.github/workflows/swa-deploy.yml` (the `VITE_API_BASE` env line, ~line 41)
- Modify: `web/src/main.ts:678-694` (export block)

**Interfaces:**
- Produces: an SWA build with zero App Service references (Task 11 verifies the live bundle again).

- [ ] **Step 1: Branch**

```bash
git checkout v1 && git pull && git checkout -b sever-appservice-fallback
```

- [ ] **Step 2: Remove `VITE_API_BASE` from the SWA workflow**

In `.github/workflows/swa-deploy.yml`, delete this line from the `env:` block of the deploy step (keep `VITE_TOKEN_URL`):

```yaml
          VITE_API_BASE: ${{ github.event_name == 'pull_request' && 'https://chd-ds-geospatial-impact-viewer-staging.azurewebsites.net' || 'https://chd-ds-geospatial-impact-viewer.azurewebsites.net' }}
```

Also update the workflow header comment ("prod token tier + prod legacy API" → "prod token tier; no legacy API — severed 2026-08").

- [ ] **Step 3: Make export failure loud when no fallback exists**

In `web/src/main.ts`, replace the export block's catch so the no-`API_BASE` build reports failure instead of redirecting to `""`:

```typescript
// Excel export: built in the browser with exceljs from platinum artifacts (ADR-0011).
// Classic (App Service) builds keep the server /api/export.xlsx as fallback; the SWA
// build has no API_BASE — a client failure there is REPORTED, never silently redirected.
{
  const exp = document.getElementById("export") as HTMLAnchorElement | null;
  if (exp) {
    if (API_BASE) exp.href = `${API_BASE}/api/export.xlsx`; // fallback URL per deploy target
    exp.addEventListener("click", async (e) => {
      e.preventDefault();
      const label = exp.textContent;
      exp.textContent = "⏳ Building spreadsheet…";
      try {
        const { downloadExport } = await import("./export");
        await downloadExport(await getToken());
      } catch (err) {
        console.error("client export failed:", err);
        if (API_BASE) {
          window.location.href = exp.href; // classic build: server fallback
        } else {
          exp.textContent = "⚠ Export failed — reload and retry";
          alert(`Spreadsheet export failed: ${err}. Reload the page and try again.`);
          return; // keep the error label
        }
      } finally {
        if (!exp.textContent?.startsWith("⚠")) exp.textContent = label;
      }
    });
  }
}
```

Note the `finally` guard: it must not clobber the error label. Match the existing block's exact surrounding code when editing (it currently sits at ~line 676).

- [ ] **Step 4: Build and verify the bundle locally**

```bash
cd web && npm run build && grep -c "azurewebsites" dist/assets/*.js; cd ..
```

Expected: `1` (the token issuer only — set via `VITE_TOKEN_URL` at CI time; locally unset, so expect `0` locally. The definitive check is on the PR preview bundle in Step 6).

- [ ] **Step 5: Commit and open PR**

```bash
git add .github/workflows/swa-deploy.yml web/src/main.ts
git commit -m "swa: sever App Service export fallback — client export failure is reported, not redirected"
git push -u origin sever-appservice-fallback
gh pr create --base v1 --title "Sever SWA → App Service export fallback" --body "Removes the last App Service reference from the SWA build (spec §1, docs/superpowers/specs/2026-08-14-multi-event-foundation-design.md). Client-export failure now surfaces an error on the SWA; the classic build's same-origin fallback is unchanged."
```

- [ ] **Step 6: Verify on the SWA preview env**

The PR comment contains the preview URL. Fetch its bundle and confirm the only `azurewebsites.net` reference is the token issuer:

```bash
PREVIEW=<preview-url-from-PR-comment>
curl -s $PREVIEW/ | grep -o 'assets/[^"]*\.js' | head -1  # bundle name
curl -s $PREVIEW/assets/<bundle>.js | grep -o 'https://[a-z0-9.-]*azurewebsites\.net' | sort -u
```

Expected: exactly one line, `https://chd-ds-token-issuer.azurewebsites.net`. Also click Export in the preview UI and confirm the workbook downloads (client path works).

- [ ] **Step 7: Merge the PR (squash or merge per repo habit), delete branch**

---

### Task 2: Event registry (`events.yaml` + `gie.events` + tests)

**Files:**
- Create: `events.yaml` (repo root, beside `data_ledger.md`)
- Create: `src/gie/events.py`
- Create: `tests/__init__.py` (empty), `tests/test_events.py`
- Modify: `pyproject.toml` (add `pyyaml` as a direct dependency — it is currently only transitive in `uv.lock`)

**Interfaces:**
- Produces: `load_events(path=REGISTRY_PATH) -> dict[str, Event]`; `get_event(event_id, path=...) -> Event`; `require_event(event_id) -> str` (validate-and-return, for pipeline `EVENT` constants); `events_to_json(events: dict[str, Event]) -> str`; `EventRegistryError(ValueError)`; frozen dataclass `Event(event_id, name, hazard, onset, countries, bbox, status, external_ids)`.
- Consumed by: Tasks 4 (pipeline constants), 6 (publish), 9 (Colombia entry).

- [ ] **Step 1: Add pyyaml and create the registry**

```bash
git checkout v1 && git pull
uv add pyyaml
```

Create `events.yaml`:

```yaml
# Event registry — the single authority for which emergency events exist
# (spec docs/superpowers/specs/2026-08-14-multi-event-foundation-design.md, ADR-0027).
#
# event_id: <yyyymmdd of onset, UTC>-<countries>-<hazard>. The slug is a MNEMONIC —
# no code parses it; `countries`/`hazard` fields are authoritative. External IDs
# (GLIDE, GDACS, USGS, CEMS activations) are cross-links, never identity.
# bbox is the viewer fly-to hint [west, south, east, north] — tune freely.
events:
  - event_id: 20260624-ve-earthquake
    name: Venezuela earthquake
    hazard: earthquake
    onset: 2026-06-24
    countries: [VE]
    bbox: [-68.2, 9.9, -66.0, 11.2]
    status: active
    external_ids:
      cems_activation: EMSR884
```

(bbox = generous envelope around the current hardcoded map view, center `[-67.03, 10.59]` in `web/src/main.ts:97` — a fly-to hint, adjustable.)

- [ ] **Step 2: Write the failing tests**

`tests/test_events.py`:

```python
"""Registry loading + validation. Uses tmp_path fixtures — never the real events.yaml,
except one smoke test that the checked-in registry is itself valid."""

import pytest

from gie import events


VALID = """\
events:
  - event_id: 20260624-ve-earthquake
    name: Venezuela earthquake
    hazard: earthquake
    onset: 2026-06-24
    countries: [VE]
    bbox: [-68.2, 9.9, -66.0, 11.2]
    status: active
    external_ids:
      cems_activation: EMSR884
  - event_id: 20260812-co-earthquake
    name: Colombia earthquake
    hazard: earthquake
    onset: 2026-08-12
    countries: [CO]
    bbox: [-75.0, 4.0, -72.0, 8.0]
    status: active
"""


def _write(tmp_path, text):
    p = tmp_path / "events.yaml"
    p.write_text(text)
    return p


def test_load_valid_registry(tmp_path):
    evs = events.load_events(_write(tmp_path, VALID))
    assert set(evs) == {"20260624-ve-earthquake", "20260812-co-earthquake"}
    ve = evs["20260624-ve-earthquake"]
    assert ve.countries == ["VE"]
    assert ve.external_ids["cems_activation"] == "EMSR884"
    assert evs["20260812-co-earthquake"].external_ids == {}


def test_duplicate_event_id_raises(tmp_path):
    dup = VALID.replace("20260812-co-earthquake", "20260624-ve-earthquake")
    with pytest.raises(events.EventRegistryError, match="duplicate"):
        events.load_events(_write(tmp_path, dup))


def test_missing_required_field_raises(tmp_path):
    broken = VALID.replace("    hazard: earthquake\n", "", 1)
    with pytest.raises(events.EventRegistryError, match="hazard"):
        events.load_events(_write(tmp_path, broken))


def test_bad_status_raises(tmp_path):
    broken = VALID.replace("status: active", "status: ongoing", 1)
    with pytest.raises(events.EventRegistryError, match="status"):
        events.load_events(_write(tmp_path, broken))


def test_bad_bbox_raises(tmp_path):
    broken = VALID.replace("[-68.2, 9.9, -66.0, 11.2]", "[-68.2, 9.9]")
    with pytest.raises(events.EventRegistryError, match="bbox"):
        events.load_events(_write(tmp_path, broken))


def test_unknown_event_id_raises_naming_registry(tmp_path):
    p = _write(tmp_path, VALID)
    with pytest.raises(events.EventRegistryError, match="20260101-xx-flood"):
        events.get_event("20260101-xx-flood", path=p)


def test_events_to_json_sorted_newest_first(tmp_path):
    import json

    evs = events.load_events(_write(tmp_path, VALID))
    out = json.loads(events.events_to_json(evs))
    assert [e["event_id"] for e in out["events"]] == [
        "20260812-co-earthquake",
        "20260624-ve-earthquake",
    ]


def test_checked_in_registry_is_valid():
    evs = events.load_events()  # the real events.yaml
    assert "20260624-ve-earthquake" in evs
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
uv run pytest tests/test_events.py -v
```

Expected: FAIL / errors — `gie.events` does not exist.

- [ ] **Step 4: Implement `src/gie/events.py`**

```python
"""Event registry: the single authority for which emergency events exist.

``events.yaml`` at the repo root is the source of truth (spec 2026-08-14,
ADR-0027). The event_id slug is a mnemonic — nothing parses it; the fields
(``countries``, ``hazard``, ``onset``) are authoritative. Validation raises
``EventRegistryError`` naming the file and the offending entry — a bad
registry must never half-load.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "events.yaml"

_REQUIRED = ("event_id", "name", "hazard", "onset", "countries", "bbox", "status")
_STATUSES = ("active", "closed")


class EventRegistryError(ValueError):
    """The event registry is invalid or an unknown event was requested."""


@dataclass(frozen=True)
class Event:
    event_id: str
    name: str
    hazard: str
    onset: str  # ISO date, validated
    countries: list[str]
    bbox: list[float]  # [west, south, east, north]
    status: str
    external_ids: dict[str, str] = field(default_factory=dict)


def load_events(path: Path | str = REGISTRY_PATH) -> dict[str, Event]:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), list):
        raise EventRegistryError(f"{path}: expected a top-level 'events' list")
    out: dict[str, Event] = {}
    for i, item in enumerate(raw["events"]):
        where = f"{path}: events[{i}]"
        missing = [k for k in _REQUIRED if k not in item]
        if missing:
            raise EventRegistryError(f"{where}: missing required field(s) {missing}")
        eid = item["event_id"]
        if eid in out:
            raise EventRegistryError(f"{where}: duplicate event_id {eid!r}")
        if item["status"] not in _STATUSES:
            raise EventRegistryError(
                f"{where}: status {item['status']!r} not in {_STATUSES}"
            )
        bbox = item["bbox"]
        if not (isinstance(bbox, list) and len(bbox) == 4):
            raise EventRegistryError(f"{where}: bbox must be [west, south, east, north]")
        onset = item["onset"]
        onset = onset.isoformat() if isinstance(onset, _dt.date) else str(onset)
        try:
            _dt.date.fromisoformat(onset)
        except ValueError as e:
            raise EventRegistryError(f"{where}: onset {onset!r} is not an ISO date") from e
        if not (isinstance(item["countries"], list) and item["countries"]):
            raise EventRegistryError(f"{where}: countries must be a non-empty list")
        ext = item.get("external_ids") or {}
        out[eid] = Event(
            event_id=eid,
            name=item["name"],
            hazard=item["hazard"],
            onset=onset,
            countries=[str(c) for c in item["countries"]],
            bbox=[float(v) for v in bbox],
            status=item["status"],
            external_ids={str(k): str(v) for k, v in ext.items()},
        )
    return out


def get_event(event_id: str, path: Path | str = REGISTRY_PATH) -> Event:
    events = load_events(path)
    if event_id not in events:
        raise EventRegistryError(
            f"unknown event_id {event_id!r} — not in {path}; known: {sorted(events)}"
        )
    return events[event_id]


def require_event(event_id: str, path: Path | str = REGISTRY_PATH) -> str:
    """Validate an event id against the registry and return it (for EVENT constants)."""
    return get_event(event_id, path=path).event_id


def events_to_json(events: dict[str, Event]) -> str:
    """Serialize the registry for the SPA (platinum/events.json), newest first."""
    ordered = sorted(events.values(), key=lambda e: e.onset, reverse=True)
    return json.dumps({"events": [asdict(e) for e in ordered]}, indent=2)
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
uv run pytest tests/test_events.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add events.yaml src/gie/events.py tests/ pyproject.toml uv.lock
git commit -m "events: registry (events.yaml) + gie.events loader — single authority for emergency events"
```

---

### Task 3: Event-aware `blob_path` / `az_path` (the choke point)

**Files:**
- Modify: `src/gie/config.py:109-131` (`blob_path`, `az_path`)
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Settings.blob_path(layer, *parts, event: str | None) -> str` and `Settings.az_path(layer, *parts, event: str | None) -> str` — `event` is **keyword-only with no default**: `event="<id>"` inserts `event=<id>` immediately after the tier prefix; `event=None` is the explicit opt-out producing the legacy/shared path (reference data, App Service). Omitting it is a TypeError. Every caller in the codebase must pass it (Task 4).

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import pytest

from gie.config import Settings


def test_event_path_inserted_after_tier_prefix():
    s = Settings()
    assert (
        s.blob_path("bronze", "source=x", "f.parquet", event="20260812-co-earthquake")
        == "ds-geospatial-impact-estimates/bronze/event=20260812-co-earthquake/source=x/f.parquet"
    )


def test_event_none_is_legacy_path():
    s = Settings()
    assert (
        s.blob_path("bronze", "source=codab", "adm0=CO", "adm1.parquet", event=None)
        == "ds-geospatial-impact-estimates/bronze/source=codab/adm0=CO/adm1.parquet"
    )


def test_event_omitted_is_a_typeerror():
    with pytest.raises(TypeError):
        Settings().blob_path("bronze", "source=x")


def test_prod_tier_suffix_composes_with_event():
    s = Settings(tier="prod")
    assert (
        s.blob_path("platinum", "meta", "sources.json", event="20260624-ve-earthquake")
        == "ds-geospatial-impact-estimates/platinum-prod/event=20260624-ve-earthquake/meta/sources.json"
    )
    # bronze/silver are untiered — event still applies
    assert s.blob_path("silver", "x.parquet", event="e1").startswith(
        "ds-geospatial-impact-estimates/silver/event=e1/"
    )


def test_az_path_wraps_blob_path():
    s = Settings()
    assert (
        s.az_path("gold", "facts.parquet", event="e1")
        == "az://projects/ds-geospatial-impact-estimates/gold/event=e1/facts.parquet"
    )
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: TypeErrors in the wrong direction / assertion failures — current signature has no `event`.

- [ ] **Step 3: Implement**

In `src/gie/config.py`, change the two methods (docstrings included — they are the contract):

```python
    def blob_path(
        self,
        layer: Literal["bronze", "silver", "gold", "platinum"],
        *parts: str,
        event: str | None,
    ) -> str:
        """Path within the container (no ``az://``/container) — for stratus writes.

        ``event`` is required (keyword-only, no default — spec 2026-08-14 /
        ADR-0027): pass the event id to write under ``<tier>/event=<id>/...``,
        or ``event=None`` as the *explicit* opt-out for shared reference data
        (CODAB) and the legacy layout the App Service is pinned to. There is
        deliberately no default: a caller that doesn't name its event fails
        loudly instead of silently writing the legacy tree.

        ``gold`` and ``platinum`` are tier-aware (``-prod`` suffix when
        ``tier=prod``); ``bronze``/``silver`` are the shared working copy.
        """
        prefix = {
            "bronze": self.bronze_prefix,
            "silver": self.silver_prefix,
            "gold": self._served(self.gold_prefix),
            "platinum": self.platinum_prefix,
        }[layer]
        segs = [self.project_prefix, prefix]
        if event is not None:
            segs.append(f"event={event}")
        return "/".join([*segs, *parts])

    def az_path(
        self,
        layer: Literal["bronze", "silver", "gold", "platinum"],
        *parts: str,
        event: str | None,
    ) -> str:
        """Build an ``az://`` path the DuckDB azure extension understands."""
        return f"az://{self.container}/{self.blob_path(layer, *parts, event=event)}"
```

- [ ] **Step 4: Run tests — new ones pass, and expect the rest of the suite green too**

```bash
uv run pytest -v
```

Expected: `tests/test_config.py` + `tests/test_events.py` all PASS. (Pipelines aren't imported by tests, so their now-broken calls don't fail here — Task 4 fixes them before anything runs.)

- [ ] **Step 5: Commit**

```bash
git add src/gie/config.py tests/test_config.py
git commit -m "config: blob_path/az_path take a required keyword-only event — event=<id> partitions, event=None is the explicit legacy/reference opt-out"
```

**⚠ Note for the executor:** between this commit and the end of Task 4, pipeline scripts raise TypeError if run. Do Tasks 3 and 4 back-to-back in one sitting.

---

### Task 4: Sweep all 113 call sites (34 files) to pass `event=`

Mechanical but judgment-bearing: which files get the VE event vs. the explicit `None` opt-out.

**Files (Modify — the complete caller list, from `grep -rln "blob_path(\|az_path(" src/ api/ pipelines/`):**
- **VE-event-scoped** (pass `event=EVENT`): all `pipelines/ingest_*.py` EXCEPT `ingest_codab.py`; all `pipelines/harmonize_*.py`; `pipelines/aggregate_damage.py`, `pipelines/build_platinum.py`, `pipelines/cems_coverage.py`, `pipelines/stage_serving.py`
- **Explicit opt-out (`event=None`)**: `pipelines/ingest_codab.py` (shared reference tree, spec §3), `src/gie/serving.py` (App Service pinned to legacy layout, spec §4)
- **Parameter pass-through**: `src/gie/cems_products.py` (library code used only by `cems_coverage.py` and `harmonize_cems.py` — its functions gain an `event` parameter their callers fill)
- **Untouched**: `pipelines/promote.py` (copies whole tiers by listing, never builds partition paths), `pipelines/run_all.py` (orchestrates, doesn't build paths — verify with grep)

**Interfaces:**
- Consumes: `gie.events.require_event` (Task 2), `blob_path(..., event=...)` (Task 3).
- Produces: every VE pipeline has module constant `EVENT = "20260624-ve-earthquake"`, validated by `events.require_event(EVENT)` as the first line of its `main()`.

- [ ] **Step 1: Add the EVENT constant pattern to each VE-scoped pipeline**

In each VE-scoped file, next to the existing constants (e.g. after `STAGE = "dev"`):

```python
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
```

First line of each `main()`:

```python
    events.require_event(EVENT)
```

with `from gie import events` added to imports. Then append `event=EVENT` to every `blob_path(`/`az_path(` call in the file. **The existing `*parts` (including `adm0=VE`, `code=EMSR884` segments) stay exactly as they are** — the copied VE tree preserves them (spec §4), and idempotent skip-if-present depends on paths matching the copied blobs.

Example — `pipelines/ingest_cems.py`'s `_product_blob` becomes:

```python
def _product_blob(settings, row, fname: str) -> str:
    """Immutable, version-encoded bronze key for one product version."""
    return settings.blob_path(
        "bronze",
        f"source={SOURCE}",
        f"code={ACTIVATION}",
        f"aoi={int(row['aoi_number']):02d}",
        f"product_type={row['product_type']}",
        f"v{int(row['version_number'])}_m{int(row['monitoring_number'])}",
        fname,
        event=EVENT,
    )
```

- [ ] **Step 2: Opt-outs with a comment stating why**

`pipelines/ingest_codab.py` — every call gets `event=None`, with one comment at the first site:

```python
        # event=None: CODAB is shared, country-keyed REFERENCE data outside the
        # event tree — reusable across events (spec §3).
```

`src/gie/serving.py` — every call gets `event=None`, one comment at the top of the module:

```python
# event=None throughout: the App Service serving layer is PINNED to the legacy
# un-evented layout until its retirement (spec §4). Do not event-scope these.
```

- [ ] **Step 3: `src/gie/cems_products.py` pass-through**

Its path-building function (line ~65) gains a required `event: str | None` parameter forwarded to `blob_path(..., event=event)`; update its two callers (`pipelines/cems_coverage.py`, `pipelines/harmonize_cems.py`) to pass `event=EVENT`.

- [ ] **Step 4: Verify the sweep is complete**

```bash
# every call must now mention event= (call-site or next line for wrapped args):
grep -rn "blob_path(\|az_path(" src/ api/ pipelines/ scripts/ 2>/dev/null \
  | grep -v "def blob_path\|def az_path" > /tmp/calls.txt
uv run --group etl python - <<'EOF'
import re, pathlib, sys
bad = []
for f in set(l.split(":")[0] for l in open("/tmp/calls.txt")):
    src = pathlib.Path(f).read_text()
    for m in re.finditer(r"\b(?:blob_path|az_path)\((?:[^()]|\([^()]*\))*\)", src):
        if "event=" not in m.group(0):
            bad.append((f, m.group(0)[:80]))
print("\n".join(map(str, bad)) or "all call sites pass event=")
sys.exit(1 if bad else 0)
EOF
# and everything still compiles:
uv run --group etl python -m compileall -q src api pipelines && echo COMPILE_OK
uv run pytest -q
```

Expected: `all call sites pass event=`, `COMPILE_OK`, tests green.

- [ ] **Step 5: Smoke-run one idempotent pipeline against the real lake — AFTER Task 5's copy**

(Deferred marker: this smoke-run happens as Task 5 Step 5, once the copied tree exists — running now would write a fresh event tree next to the un-copied legacy one. Nothing to do in this step; it exists so the executor doesn't run pipelines early.)

- [ ] **Step 6: Commit**

```bash
git add src/ api/ pipelines/
git commit -m "pipelines: every blob path names its event — VE scripts pinned to 20260624-ve-earthquake, codab + App Service serving explicitly opted out"
```

---

### Task 5: Server-side copy of the VE tree under its event (+ verification)

**Files:**
- Create: `scripts/copy_event_tree.py` (modeled directly on `pipelines/promote.py`'s server-side copy: DataLake `get_paths` listing, skip directory markers, pre-create HNS destination dirs, resume by same-size skip)

**Interfaces:**
- Consumes: `gie.config.load_settings`, `gie.events.require_event`.
- Produces: the working tiers duplicated under `event=20260624-ve-earthquake/`; a printed per-tier verification table (file counts + total bytes, source vs copy) — the recorded evidence for the eventual legacy freeze (spec §5). Exits non-zero on any mismatch.

- [ ] **Step 1: Write the script**

```python
"""One-time server-side copy: legacy un-evented tiers -> event=<id>/ (spec §4).

Copies bronze/silver/gold/platinum working tiers into their event-keyed layout:
  <tier>/<rest>  ->  <tier>/event=<EVENT>/<rest>
COPY, never move — the legacy tree stays untouched for every live reader.

Exclusions:
  * source=codab/ (shared reference tree, stays outside events — spec §3)
  * anything already under event= (re-run safety; never recurse)
  * gold-prod/ + platinum-prod/ (published copies are regenerated by promote.py)

Server-side (Copy Blob within the account) like promote.py: data never transits
this machine. Re-runnable: same-size existing copies are skipped. Ends with a
count+bytes verification table per tier and exits non-zero on mismatch.

Run: uv run --group etl python scripts/copy_event_tree.py [--dry-run]
"""

from __future__ import annotations

import sys
import time

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from azure.storage.filedatalake import DataLakeServiceClient

from gie import events
from gie.config import load_settings

EVENT = events.require_event("20260624-ve-earthquake")
TIERS = ["bronze", "silver", "gold", "platinum"]  # working copies only


def _files(fs, project_prefix: str, tier: str) -> dict[str, int]:
    """name -> size for real files under a tier ({} if tier absent)."""
    try:
        return {
            p.name: p.content_length
            for p in fs.get_paths(path=f"{project_prefix}/{tier}", recursive=True)
            if not p.is_directory
        }
    except Exception as e:  # tier truly absent is the only acceptable miss
        print(f"  {tier}/: listing failed ({e}); treating as absent")
        return {}


def main() -> None:
    dry = "--dry-run" in sys.argv
    s = load_settings("dev")
    dfs_url = f"https://{s.account_name}.dfs.core.windows.net"
    src_fs = DataLakeServiceClient(dfs_url, credential=s.sas_token()).get_file_system_client(s.container)
    dst_fs = DataLakeServiceClient(dfs_url, credential=s.sas_token(write=True)).get_file_system_client(s.container)
    dst_blob = BlobServiceClient(f"https://{s.account_host}", credential=s.sas_token(write=True))
    read_sas = s.sas_token()

    failures = 0
    for tier in TIERS:
        base = f"{s.project_prefix}/{tier}/"
        all_files = _files(src_fs, s.project_prefix, tier)
        src = {
            n: sz
            for n, sz in all_files.items()
            if not n[len(base):].startswith("event=")          # never recurse
            and not n[len(base):].startswith("source=codab/")  # shared reference
        }
        done = {
            n: sz for n, sz in all_files.items()
            if n[len(base):].startswith(f"event={EVENT}/")
        }
        copied = skipped = 0
        made_dirs: set[str] = set()
        for name, size in sorted(src.items()):
            dst = f"{base}event={EVENT}/{name[len(base):]}"
            if done.get(dst) == size:
                skipped += 1
                continue
            if dry:
                copied += 1
                continue
            dpath = dst.rsplit("/", 1)[0]
            if dpath not in made_dirs:
                try:
                    dst_fs.create_directory(dpath)
                except ResourceExistsError:
                    pass
                made_dirs.add(dpath)
            url = f"https://{s.account_host}/{s.container}/{name}?{read_sas}"
            poller = dst_blob.get_blob_client(s.container, dst).start_copy_from_url(url)
            while poller["copy_status"] == "pending":
                time.sleep(0.2)
                poller = dst_blob.get_blob_client(s.container, dst).get_blob_properties().copy.__dict__
            copied += 1

        # verification: recount the copy and compare counts + total bytes
        post = {
            n: sz for n, sz in _files(dst_fs, s.project_prefix, tier).items()
            if n[len(base):].startswith(f"event={EVENT}/")
        }
        ok = dry or (len(post) == len(src) and sum(post.values()) == sum(src.values()))
        failures += 0 if ok else 1
        print(
            f"{tier}/: src {len(src)} files / {sum(src.values()):,} B -> "
            f"copy {len(post)} files / {sum(post.values()):,} B  "
            f"(copied {copied}, skipped {skipped}) {'[dry-run] ' if dry else ''}{'OK' if ok else 'MISMATCH'}"
        )
    if failures:
        sys.exit(f"{failures} tier(s) MISMATCHED — do not proceed to cutover.")
    print("done — record this table in data_ledger.md (freeze evidence, spec §5).")


if __name__ == "__main__":
    main()
```

(The `start_copy_from_url` polling detail may need adjusting against the installed SDK — `promote.py` lines 80+ have the working pattern; **reuse promote.py's copy/poll code verbatim** if it differs from the above.)

- [ ] **Step 2: Dry-run**

```bash
uv run --group etl python scripts/copy_event_tree.py --dry-run
```

Expected: per-tier table with plausible counts (thousands of bronze files; nonzero all four tiers), zero writes.

- [ ] **Step 3: Real run**

```bash
uv run --group etl python scripts/copy_event_tree.py
```

Expected: all four tiers `OK`. Re-run once more — expect `copied 0, skipped <all>` (idempotency proof).

- [ ] **Step 4: Record the verification table in `data_ledger.md`**

Add a row: source `all`, layer `all`, dataset "VE tree copied to event=20260624-ve-earthquake (spec §4)", path `ds-geospatial-impact-estimates/*/event=20260624-ve-earthquake`, detail = the printed per-tier counts/bytes table, status `ingested`.

- [ ] **Step 5: Smoke-run one idempotent pipeline against the copied tree (the deferred Task 4 Step 5)**

```bash
uv run --group etl python pipelines/ingest_cems.py
```

Expected: runs clean, skips already-present products (they exist at the event-keyed paths via the copy), lands any newly delivered EMSR884 products under `bronze/event=20260624-ve-earthquake/...`. If it instead re-downloads everything, the path construction diverged from the copied layout — STOP and diff the paths.

- [ ] **Step 6: Commit**

```bash
git add scripts/copy_event_tree.py data_ledger.md
git commit -m "migration: server-side copy of VE tiers under event=20260624-ve-earthquake, with count+bytes verification"
```

---

### Task 6: Publish `events.json` to platinum

**Files:**
- Create: `pipelines/publish_events.py`

(Spec §2 letter says `stage_serving.py` publishes it; deliberate deviation: `stage_serving.py` is a VE-specific serving-geometry stager, while the registry is global — a dedicated tiny pipeline keeps one-responsibility-per-file. Noted here so the spec/plan don't silently disagree.)

**Interfaces:**
- Consumes: `gie.events.load_events` / `events_to_json`, `gie.blobio.uploader`/`upload` (same helpers `stage_serving.py` uses).
- Produces: `platinum/events.json` (working tier; `promote.py` carries it to `platinum-prod` automatically since it copies the whole tier). The SPA (Task 7) reads `${base_url}/${platinum_dir}/events.json`.

- [ ] **Step 1: Write the pipeline**

```python
"""Publish the event registry to the served tier: events.yaml -> platinum/events.json.

The SPA's landing page and event routes read this (spec §2/§6). Lives at the
platinum ROOT (not under any event=) — it is the index OF events. promote.py
copies the whole platinum tier, so prod picks it up at the next promote.

Run: uv run --group etl python pipelines/publish_events.py
"""

from __future__ import annotations

from gie import blobio, events
from gie.config import load_settings

STAGE = "dev"


def main() -> None:
    settings = load_settings(STAGE)
    evs = events.load_events()  # raises EventRegistryError on an invalid registry
    payload = events.events_to_json(evs).encode()
    dest = settings.blob_path("platinum", "events.json", event=None)  # tier ROOT: the index OF events
    blobio.upload(blobio.uploader(settings), payload, dest)
    print(f"events.json <- {dest}  ({len(evs)} events: {', '.join(sorted(evs))})")


if __name__ == "__main__":
    main()
```

(Check `gie/blobio.py` for the exact `upload` signature before writing — `stage_serving.py:36` shows `blobio.upload(fs, data, dest_blob)` with `fs = blobio.uploader(settings)`; if `upload` expects bytes-like it works as written, otherwise adapt to the module's helper.)

- [ ] **Step 2: Run it**

```bash
uv run --group etl python pipelines/publish_events.py
```

Expected: `events.json <- ds-geospatial-impact-estimates/platinum/events.json (1 events: 20260624-ve-earthquake)`.

- [ ] **Step 3: Verify it's readable through the token issuer path (what the SPA will do)**

```bash
TOK=$(curl -s "https://chd-ds-token-issuer.azurewebsites.net/api/token?app=satellite-viewer&tier=staging")
BASE=$(echo $TOK | python3 -c "import json,sys; t=json.load(sys.stdin); print(t['base_url']+'/'+t['platinum_dir'])")
SAS=$(echo $TOK | python3 -c "import json,sys; print(json.load(sys.stdin)['sas'])")
curl -s "$BASE/events.json?$SAS" | head -20
```

Expected: the JSON with the VE event. (Confirms no token-issuer change was needed — directory-scoped SAS covers it.)

- [ ] **Step 4: Commit**

```bash
git add pipelines/publish_events.py
git commit -m "serving: publish events.yaml -> platinum/events.json for the SPA landing page and routes"
```

---

### Task 7: SPA — event context, hash routes, event-scoped platinum reads

All `web/**` work (Tasks 7+8) happens on one feature branch with one PR, verified on the SWA preview env before merge.

**Files:**
- Create: `web/src/events.ts`
- Modify: `web/src/main.ts` (platinum path construction; the map init; panel `h1`)
- Modify: `web/src/export.ts` (platinum base passed in already via token — confirm it uses the same helper)

**Interfaces:**
- Consumes: `platinum/events.json` (Task 6), the existing `getToken()` token shape (`{base_url, platinum_dir, sas}`).
- Produces (for Task 8): `web/src/events.ts` exporting:
  - `interface EventInfo { event_id: string; name: string; hazard: string; onset: string; countries: string[]; bbox: [number, number, number, number]; status: string; external_ids: Record<string, string> }`
  - `fetchEvents(tok): Promise<EventInfo[]>` (reads `${tok.base_url}/${tok.platinum_dir}/events.json?${tok.sas}`)
  - `currentEventId(): string | null` (parses `location.hash` of the form `#/e/<event_id>`)
  - `eventDir(tok, eventId: string): string` → `` `${tok.base_url}/${tok.platinum_dir}/event=${eventId}` `` — **the single place the SPA builds an event-scoped platinum base**.

- [ ] **Step 1: Branch**

```bash
git checkout v1 && git pull && git checkout -b multi-event-spa
```

- [ ] **Step 2: Write `web/src/events.ts`**

```typescript
// Event registry access + hash routing. The registry (platinum/events.json,
// published from events.yaml) is the single authority for which events exist.
// Routes: "#/e/<event_id>" is an event view; empty/other hash -> landing page.

export interface EventInfo {
  event_id: string;
  name: string;
  hazard: string;
  onset: string;
  countries: string[];
  bbox: [number, number, number, number];
  status: string;
  external_ids: Record<string, string>;
}

export async function fetchEvents(tok: any): Promise<EventInfo[]> {
  const r = await fetch(`${tok.base_url}/${tok.platinum_dir}/events.json?${tok.sas}`);
  if (!r.ok) throw new Error(`events.json fetch failed: HTTP ${r.status}`);
  const data = await r.json();
  if (!Array.isArray(data?.events)) throw new Error("events.json: malformed registry");
  return data.events as EventInfo[];
}

export function currentEventId(): string | null {
  const m = location.hash.match(/^#\/e\/([A-Za-z0-9-]+)$/);
  return m ? m[1] : null;
}

// The ONE place an event-scoped platinum base URL is built.
export function eventDir(tok: any, eventId: string): string {
  return `${tok.base_url}/${tok.platinum_dir}/event=${eventId}`;
}
```

- [ ] **Step 3: Thread the event through `main.ts`'s data reads**

`main.ts` builds platinum URLs in several places (`fetchMeta` at line ~19, `setupPmtiles` at ~line 705, hyparquet reads, `export.ts`'s base). Mechanical transform: everywhere the code concatenates `${tok.base_url}/${tok.platinum_dir}` (grep: `platinum_dir`), route it through `eventDir(tok, EVENT_ID)` instead, where at module scope:

```typescript
import { currentEventId, eventDir, fetchEvents, type EventInfo } from "./events";

const EVENT_ID = currentEventId(); // null -> landing page (Task 8); non-null -> event view
```

Guard: the whole map-init block only runs when `EVENT_ID !== null` (Task 8 Step 2 adds the split; in this task, temporarily default `null` → redirect `location.hash = "#/e/20260624-ve-earthquake"` + reload so the app stays usable mid-branch).

`export.ts` receives the token today (`downloadExport(await getToken())`) and builds `${base}/meta/export_meta.json` — change its signature to `downloadExport(tok, dir: string)` and pass `eventDir(tok, EVENT_ID!)`; inside, `base` becomes the passed `dir`.

The map init (line ~94) replaces the hardcoded `center: [-67.03, 10.59], zoom: 11` with a fly-to from the registry bbox after events load:

```typescript
map.fitBounds([[ev.bbox[0], ev.bbox[1]], [ev.bbox[2], ev.bbox[3]]], { padding: 40, duration: 0 });
```

and the panel `<h1>` (currently hardcoded `Venezuela earthquake (EMSR884)` in `web/index.html`) becomes `id="event-title"` filled from `ev.name` (+ CEMS activation from `ev.external_ids.cems_activation` when present).

- [ ] **Step 4: Build + manual verification on staging data**

```bash
cd web && npm run build && npm run dev
```

In the dev server: `#/e/20260624-ve-earthquake` loads the VE viewer exactly as before (data comes from the copied `event=` tree); every layer toggles; export downloads; `#/e/garbage` shows the failed-fetch behavior (proper error card lands in Task 8).

- [ ] **Step 5: Commit (on the branch — PR comes after Task 8)**

```bash
git add web/src/events.ts web/src/main.ts web/src/export.ts web/index.html
git commit -m "spa: event-scoped platinum reads + #/e/<event_id> hash routes, view + title from the event registry"
```

---

### Task 8: SPA — landing page, event dropdown, unknown-event error card

**Files:**
- Create: `web/src/landing.ts`
- Modify: `web/src/main.ts` (route split: landing vs event view), `web/index.html` (landing container + event dropdown in the panel), `web/src/style.css` (landing card styles, match the existing floating-panel aesthetic)

**Interfaces:**
- Consumes: `fetchEvents`, `currentEventId`, `EventInfo` from Task 7.
- Produces: `renderLanding(events: EventInfo[], container: HTMLElement): void`; `renderEventError(eventId: string, events: EventInfo[], container: HTMLElement): void`.

- [ ] **Step 1: Write `web/src/landing.ts`**

```typescript
// Landing page ("/" i.e. empty hash): one card per event from the registry.
// Also the unknown-event error card — an explicit failure state, never a
// blank map and never a silent fallback to another event.

import type { EventInfo } from "./events";

const card = (ev: EventInfo) => `
  <a class="event-card" href="#/e/${ev.event_id}">
    <span class="event-status event-status-${ev.status}">${ev.status}</span>
    <h2>${ev.name}</h2>
    <p>${ev.hazard} · onset ${ev.onset} · ${ev.countries.join(", ")}</p>
  </a>`;

export function renderLanding(events: EventInfo[], container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <img src="/ocha_logo.svg" alt="OCHA" width="117" height="28" />
      <h1>Damage Exposure Viewer</h1>
      <p class="sub">Multi-source satellite damage estimates, by emergency event</p>
      ${events.map(card).join("")}
    </div>`;
  container.hidden = false;
}

export function renderEventError(eventId: string, events: EventInfo[], container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <h1>Unknown event</h1>
      <p class="sub">“${eventId}” is not in the event registry. Available events:</p>
      ${events.map(card).join("")}
    </div>`;
  container.hidden = false;
}
```

- [ ] **Step 2: Route split in `main.ts` + dropdown**

`web/index.html` gains, directly under `<body>`: `<div id="landing" hidden></div>`, and in the panel (above the Sources group) an event switcher:

```html
      <div class="group">
        <div class="label">Event</div>
        <select id="eventSwitch"></select>
      </div>
```

`main.ts` boot sequence becomes:

```typescript
async function boot() {
  const tok = await getToken();
  const events = await fetchEvents(tok);
  const landing = document.getElementById("landing")!;
  if (!EVENT_ID) return renderLanding(events, landing);
  const ev = events.find((e) => e.event_id === EVENT_ID);
  if (!ev) return renderEventError(EVENT_ID, events, landing);
  initViewer(ev, tok, events); // the existing init path, wrapped
}
```

`initViewer` fills `#eventSwitch` with all events (current selected) and on change does `location.hash = \`#/e/${id}\`; location.reload();` — a full reload per switch is deliberate (YAGNI: no in-place teardown of map sources/layers), and `window.addEventListener("hashchange", () => location.reload())` covers back/forward. Landing/error views hide the map + panels (`#map`, `#panel`, the FAB get `hidden` when landing is shown).

- [ ] **Step 3: Style the landing** (match the floating-panel look: same font stack, card = white rounded box with the panel's shadow; `.event-status-active` green pill, `-closed` gray).

- [ ] **Step 4: Build + full manual pass**

```bash
cd web && npm run build && npm run dev
```

Verify: bare URL → landing with one VE card; card click → VE viewer; dropdown switches (after Task 9 there'll be two events); `#/e/garbage` → error card listing available events; direct deep link works on refresh.

- [ ] **Step 5: Commit, push, open the PR**

```bash
git add web/
git commit -m "spa: landing page of registry events, in-viewer event switcher, explicit unknown-event error card"
git push -u origin multi-event-spa
gh pr create --base v1 --title "Multi-event SPA: landing page + #/e/<event_id> routes" --body "Spec §6 (docs/superpowers/specs/2026-08-14-multi-event-foundation-design.md). Reads platinum/events.json; event-scoped platinum reads via the copied event tree. Verify on the SWA preview env (staging tier) before merge."
```

- [ ] **Step 6: Verify on the SWA preview env** — landing, VE event view (all layers, tooltips, export), error card. **Do not merge yet** — merge happens in Task 11 (release), after Colombia exists so the landing page ships showing both events.

---

### Task 9: Colombia onboarding (registry entry + CODAB)

**Files:**
- Modify: `events.yaml`, `pipelines/ingest_codab.py`
- Test: `tests/test_events.py::test_checked_in_registry_is_valid` (already exists — re-run covers the new entry)

**Interfaces:**
- Consumes: registry loader (Task 2); `blob_path(..., event=None)` for CODAB (Task 4).
- Produces: the CO event registered; `bronze/source=codab/adm0=CO/adm{0-3}.parquet` in the shared reference tree.

- [ ] **Step 1: Fix the Colombia event facts from USGS**

Look up the earthquake on https://earthquake.usgs.gov (event page for the August 2026 Colombia quake): onset date (UTC), magnitude, epicenter, USGS event id, and GDACS id if listed. The `event_id` is `<yyyymmdd>-co-earthquake` from that UTC onset (combine codes, e.g. `-co-ve-`, only if the response formally spans borders). Set bbox as epicenter ±1.5° as the starting fly-to hint.

- [ ] **Step 2: Add the registry entry**

Append to `events.yaml` (values from Step 1 — the shape, with placeholders that MUST be replaced before commit):

```yaml
  - event_id: 20260812-co-earthquake   # <- actual UTC onset date
    name: Colombia earthquake
    hazard: earthquake
    onset: 2026-08-12                  # <- actual
    countries: [CO]
    bbox: [-75.5, 4.5, -72.5, 7.5]     # <- epicenter ±1.5°
    status: active
    external_ids:
      usgs: <usgs-event-id>
      # cems_activation / glide / gdacs: add as issued
```

```bash
uv run pytest tests/test_events.py -v   # registry still valid
```

- [ ] **Step 3: Parametrize `ingest_codab.py`**

Replace the constants with argparse (this is the genuinely multi-country reference loader):

```python
import argparse

def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest OCHA CODAB admin boundaries (shared reference tree)")
    ap.add_argument("--iso3", required=True, help="country ISO3, e.g. VEN, COL")
    ap.add_argument("--adm0", required=True, help="adm0 partition code, e.g. VE, CO")
    args = ap.parse_args()
    iso3, adm0 = args.iso3.upper(), args.adm0.upper()
    ...
```

with `ISO3`/`ADM0` uses replaced by `iso3`/`adm0` throughout `main()` (paths keep `event=None` + the comment from Task 4). Update the module docstring's Run line: `uv run --group etl python pipelines/ingest_codab.py --iso3 COL --adm0 CO`.

- [ ] **Step 4: Run it for Colombia, republish events.json**

```bash
uv run --group etl python pipelines/ingest_codab.py --iso3 COL --adm0 CO
uv run --group etl python pipelines/publish_events.py
```

Expected: 4 admin levels landed under `bronze/source=codab/adm0=CO/`; `events.json` now lists 2 events. (Per-source CO damage-product ingestion is ops work as products/activations arrive — new activation constants or scripts per source, following the VE patterns; explicitly not in this plan.)

- [ ] **Step 5: Commit**

```bash
git add events.yaml pipelines/ingest_codab.py data_ledger.md
git commit -m "colombia: register 20260812-co-earthquake; ingest_codab takes --iso3/--adm0 (COL landed to shared reference tree)"
```

(Include the `data_ledger.md` row `ingest_codab` writes/append one manually if the script doesn't.)

---

### Task 10: ADR-0027 + docs

**Files:**
- Create: `docs/decisions/0027-event-keyed-partitioning-and-registry.md` (next number after 0026; copy the shape of `docs/decisions/template.md`)

**Interfaces:** none (documentation).

- [ ] **Step 1: Write the ADR** — MADR format, frontmatter `status: "accepted"`, `date:` (today), deciders: data science team (zackarno). Content requirements (the valuable part is the rejected options):
  - **Context:** single-event `adm0=`-keyed layout meets a second event (Colombia); country is an attribute of an event, not an identity (same-country repeats; cross-border events).
  - **Options considered:** (1) `event=` partition above `source=`, country demoted to a column — chosen; (2) country-first (`adm0=` above `event=`) — rejected: no reader prunes by country, cross-border events straddle partitions; (3) per-event storage containers/prefixes (full isolation) — rejected: multiplies token-issuer allowlist entries and pipeline config for no reader benefit; (4) keep `adm0=` inside the event tree for new events — rejected: splitting as-received cross-border deliveries violates ADR-0005's immutable as-received bronze.
  - **Registry:** `events.yaml` in-repo as sole authority; slug is a mnemonic (never parsed); external IDs (GLIDE/GDACS/USGS/CEMS) as metadata because issuance lags onset. Rejected: Postgres event table (ADR-0002's trigger not met), deriving events from blob listing (existence ≠ registration; fails loudly nowhere).
  - **Consequences:** required `event=` kwarg at the choke point; `event=None` as explicit opt-out (CODAB reference tree, App Service legacy pin); VE tree copied not moved; legacy deletion gated on App Service retirement (amends spec §5). Amends ADR-0005 (path scheme gains the event segment); does not supersede it.
- [ ] **Step 2: Cross-link** — add one line to ADR-0005 under its Decision Outcome: `Amended by ADR-0027: paths gain a leading event=<id> segment; the idempotency model is unchanged.`
- [ ] **Step 3: Commit**

```bash
git add docs/decisions/0027-event-keyed-partitioning-and-registry.md docs/decisions/0005-idempotent-versioned-bronze-ingestion.md
git commit -m "adr: 0027 event-keyed partitioning + event registry (amends 0005)"
```

---

### Task 11: Release — merge the SPA PR, promote, verify prod

**Files:** none new (operations + verification).

- [ ] **Step 1: Re-verify the preview** — the Task 8 PR preview (staging tier) now shows both events on the landing page (staging reads working platinum, which has `events.json` with 2 events and the VE event tree). Full manual pass per Task 8 Step 4.
- [ ] **Step 2: Promote the served tiers** so prod data contains the event tree + registry **before** the prod SPA needs them:

```bash
uv run --group etl python pipelines/promote.py --dry-run   # sanity: includes platinum/event=... + events.json
uv run --group etl python pipelines/promote.py
```

- [ ] **Step 3: Merge the `multi-event-spa` PR** → push to `v1` deploys SWA prod.
- [ ] **Step 4: Verify live prod**

```bash
curl -s https://ashy-sea-03134990f.7.azurestaticapps.net/ | grep -o 'assets/[^"]*\.js'
# fetch that bundle; expect the token issuer as the ONLY azurewebsites.net reference:
curl -s https://ashy-sea-03134990f.7.azurestaticapps.net/assets/<bundle>.js \
  | grep -o 'https://[a-z0-9.-]*azurewebsites\.net' | sort -u
```

and in a browser: landing page shows both events; VE deep link `#/e/20260624-ve-earthquake` renders all layers + export; unknown id shows the error card. The classic App Service URL still serves the old single-event viewer unchanged (its build/data path untouched).

- [ ] **Step 5: Post-release bookkeeping** — file the custom-domain CNAME request with IT (spec §6: two free custom domains on SWA Free tier, target `ashy-sea-03134990f.7.azurestaticapps.net`); update the team-KB app page (`ds-knowledge-base/apps/chd-ds-geospatial-impact-viewer.md` — it is marked stale; note the severed App Service dependency, multi-event routes, events.json, and that App Service CI exists via `azure-deploy.yml`) via the KB worktree + PR flow. The legacy-tree freeze is NOT actioned here — it is gated on the App Service retirement decision (spec §5); propose that retirement as its own follow-up.

---

## Self-review notes (spec coverage)

- Spec §1 → Task 1; §2 → Tasks 2, 6 (deviation: dedicated `publish_events.py` instead of extending `stage_serving.py` — noted in Task 6); §3 → Tasks 3, 4 (deviation: `--event` CLI flag materialized as required kwarg + validated constants — noted in Global Constraints); §4 → Task 5; §5 → gated, documented in Tasks 10/11 (deletion deliberately NOT scheduled — App Service gate); §6 → Tasks 7, 8, 11 (custom domain = IT request in 11); §7 → Task 9 (per-source CO ingestion explicitly ops, per spec "as products arrive").
- Type consistency: token shape `{base_url, platinum_dir, sas}` used identically in Tasks 6 (curl verification), 7 (`eventDir`), 8; `EventInfo`/`Event` field names match `events.yaml` keys and `events_to_json` output (dataclass `asdict`).
- Known execution risks called out inline: `start_copy_from_url` polling (Task 5 — fall back to promote.py's verbatim pattern), `blobio.upload` signature (Task 6), export `finally` guard (Task 1).
