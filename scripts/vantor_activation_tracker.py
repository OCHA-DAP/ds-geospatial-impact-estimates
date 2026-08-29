#!/usr/bin/env python3
"""Build pages/vantor-activations/data.json from the Vantor Open Data STAC catalog.

Fetches the catalog root, every event collection, and every item, and reduces them
to one JSON snapshot the tracker page renders: images per activation with the
pre/post split, publication dates, and event-to-delivery latencies.

Stdlib only — the scheduled workflow that runs this needs nothing but python3,
matching the deploy path's no-dependency rule (see pages/README.md).

Fail-loud contract: any fetch or parse failure raises and nothing is written.
A partial snapshot that silently drops an activation would defeat the page's
purpose, which is to show what Vantor has actually released. Malformed metadata
*inside* the catalog (two collections ship broken odp:event_date values) is a fact
about the data, not a fetch failure — it is recorded per-activation as
event_date_quality rather than papered over or fatal.

The file is rewritten only when the content (ignoring the volatile checked_at
stamp) differs from what is already on disk, so the daily cron produces commits
only when Vantor actually publishes something. Staleness between runs is the
page's job: it compares this snapshot against the live catalog client-side.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CATALOG_URL = "https://vantor-opendata.s3.amazonaws.com/events/catalog.json"
STAC_BROWSER = "https://radiantearth.github.io/stac-browser/#/external/"
OUT_PATH = Path(__file__).resolve().parent.parent / "pages" / "vantor-activations" / "data.json"
TIMEOUT = 60
MAX_WORKERS = 16


def fetch_json(url: str) -> dict:
    """GET a URL and parse it as JSON, raising with the URL on any failure."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "OCHA-DAP vantor-activation-tracker"}), timeout=TIMEOUT) as r:
            return json.load(r)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
        raise RuntimeError(f"fetch failed: {url}: {e}") from e


def child_links(doc: dict, rel: str) -> list[str]:
    return [link["href"] for link in doc.get("links", []) if link.get("rel") == rel]


def normalise_event_date(raw: str | None) -> tuple[str | None, str]:
    """Return (ISO date or None, quality flag).

    The catalog ships three shapes: a clean ISO datetime, nothing at all (the two
    collections migrated from the Maxar bucket), and malformed strings like
    '2026-04-24:T00.00.00Z'. The first 10 characters are a valid date in every
    non-missing case seen so far; anything else is reported, not guessed at.
    """
    if raw is None:
        return None, "missing"
    head = raw[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", head):
        quality = "ok" if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", raw) else "malformed"
        return head, quality
    return None, "malformed"


def summarise_collection(url: str) -> dict:
    col = fetch_json(url)
    cid = col["id"]

    item_urls = child_links(col, "item")
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        items = list(pool.map(fetch_json, item_urls))

    phases: dict[str, list[dict]] = {"pre": [], "post": [], "unknown": []}
    for item in items:
        props = item["properties"]
        phases.get(props.get("phase"), phases["unknown"]).append(props)

    event_date, quality = normalise_event_date(col.get("odp:event_date"))

    published = sorted(p["published"][:10] for ps in phases.values() for p in ps if p.get("published"))
    post_acquired = sorted(p["datetime"][:10] for p in phases["post"] if p.get("datetime"))
    post_published = sorted(p["published"][:10] for p in phases["post"] if p.get("published"))

    def lag(later: str) -> int | None:
        if event_date is None:
            return None
        return (date.fromisoformat(later) - date.fromisoformat(event_date)).days

    return {
        "id": cid,
        "title": col.get("title") or cid,
        "event_date": event_date,
        "event_date_raw": col.get("odp:event_date"),
        "event_date_quality": quality,
        "n_items": len(items),
        "n_pre": len(phases["pre"]),
        "n_post": len(phases["post"]),
        "n_phase_unknown": len(phases["unknown"]),
        "first_published": published[0] if published else None,
        "last_published": published[-1] if published else None,
        "first_post_acquired": post_acquired[0] if post_acquired else None,
        "first_post_published": post_published[0] if post_published else None,
        "acq_lag_days": lag(post_acquired[0]) if post_acquired else None,
        "pub_lag_days": lag(post_published[0]) if post_published else None,
        "satellites": sorted({p.get("vehicle_name") for ps in phases.values() for p in ps if p.get("vehicle_name")}),
        "bbox": (col.get("extent", {}).get("spatial", {}).get("bbox") or [None])[0],
        "stac_url": url,
        "browse_url": STAC_BROWSER + url.removeprefix("https://"),
    }


def build_snapshot() -> dict:
    root = fetch_json(CATALOG_URL)
    urls = child_links(root, "child")
    if not urls:
        # An empty catalog is far more likely a schema change than a real state of
        # the world (nine activations exist as of 2026-08); refuse to publish it.
        raise RuntimeError(f"catalog at {CATALOG_URL} lists no child collections — schema change?")

    activations = [summarise_collection(u) for u in urls]
    activations.sort(key=lambda a: a["last_published"] or "", reverse=True)

    return {
        "catalog_url": CATALOG_URL,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {
            "activations": len(activations),
            "images": sum(a["n_items"] for a in activations),
            "pre": sum(a["n_pre"] for a in activations),
            "post": sum(a["n_post"] for a in activations),
        },
        "activations": activations,
    }


def content_key(snapshot: dict) -> str:
    """The snapshot minus its volatile timestamp, for change detection."""
    return json.dumps({k: v for k, v in snapshot.items() if k != "checked_at"}, sort_keys=True)


def main() -> int:
    snapshot = build_snapshot()

    if OUT_PATH.exists():
        previous = json.loads(OUT_PATH.read_text())
        if content_key(previous) == content_key(snapshot):
            print(f"unchanged: {snapshot['totals']['images']} images across "
                  f"{snapshot['totals']['activations']} activations (as of {previous['checked_at']})")
            return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snapshot, indent=1) + "\n")
    print(f"written: {OUT_PATH} — {snapshot['totals']['images']} images across "
          f"{snapshot['totals']['activations']} activations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
