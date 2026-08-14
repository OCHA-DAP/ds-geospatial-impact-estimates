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
