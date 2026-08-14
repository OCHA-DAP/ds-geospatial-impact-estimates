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
