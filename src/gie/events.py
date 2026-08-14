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
