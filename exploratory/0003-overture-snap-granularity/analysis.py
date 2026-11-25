"""Overture-snap granularity: native vs snapped damaged-building counts per source.

Feeds docs/decisions/0017. Every source's damage is projected onto the shared
Overture base (harmonize_common, {SNAP_M} m snap) so cross-source comparison is
apples-to-apples. But a source's *native* building count differs from its count of
*distinct Overture buildings*, because footprints differ in granularity: several
fine footprints can collapse onto one Overture building. This quantifies the gap
for Microsoft, CEMS, and UNEP debris.

METHODOLOGY NOTE (see findings.md): the Overture base is cached to local disk. A
PARTIAL cache silently yields false numbers (we hit exactly this — a half-built
cache produced 69 instead of 75,656). So we RECONCILE against blob and assert the
local set matches before reading — never glob-and-trust — and write atomically so
an interrupted download can't leave a truncated file that looks complete.

Run:
  uv run --group etl --with scipy python exploratory/0003-overture-snap-granularity/analysis.py
"""
from __future__ import annotations

import glob
import io
import os
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import ocha_stratus as st  # noqa: E402
import pyogrio  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from gie.config import load_settings  # noqa: E402

STAGE, ADM0, M, SNAP_M = "dev", "VE", 32619, 20
BASE_CACHE = "/tmp/gie_base_local"


def overture_centroids(settings) -> np.ndarray:
    """Reconcile the local Overture cache against blob, then return unique building
    centroids (metric CRS). RAISES if the cache can't be made complete — a partial
    base silently produces false snap counts."""
    prefix = settings.blob_path("silver", "source=overture", f"adm0={ADM0}")
    blobs = [
        b
        for b in st.list_container_blobs(
            name_starts_with=prefix, stage=STAGE, container_name=settings.container
        )
        if b.endswith(".parquet")
    ]
    for b in blobs:
        dst = os.path.join(BASE_CACHE, b[len(prefix) + 1 :])
        if os.path.exists(dst) and os.path.getsize(dst) > 10_000:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        data = st.load_blob_data(b, stage=STAGE, container_name=settings.container)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst))  # atomic write: temp file...
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)  # ...then rename, so a file only exists once whole
    local = glob.glob(os.path.join(BASE_CACHE, "region=*", "*.parquet"))
    want = Counter(b.split("region=")[1].split("/")[0] for b in blobs)
    have = Counter(f.split("region=")[1].split("/")[0] for f in local)
    assert want == have, f"cache OUT OF SYNC with blob (fail loud): want {want}, have {have}"
    cents, ids = [], []
    for f in local:
        g = gpd.read_parquet(f, columns=["id", "geometry"])
        if g.crs is None:
            g = g.set_crs(4326)
        c = g.to_crs(M).geometry.centroid
        cents.append(np.c_[c.x.values, c.y.values])
        ids.append(g["id"].values)
    xy = np.vstack(cents)
    _, uniq = np.unique(np.concatenate(ids), return_index=True)  # dedupe cross-region dups
    return xy[uniq]


def report(name: str, xy: np.ndarray, tree: cKDTree, n_native: int) -> None:
    d, idx = tree.query(xy, k=1, distance_upper_bound=SNAP_M)
    hit = np.isfinite(d)
    distinct = len(np.unique(idx[hit]))
    print(
        f"  {name:26s} native={n_native:6,}  snapped-distinct={distinct:6,}  "
        f"collapse={hit.sum() - distinct:5,}  dropped={(~hit).sum():4,}  "
        f"gap={100 * (distinct / n_native - 1):+.0f}%"
    )


def _silver(settings, *parts):
    return gpd.read_parquet(
        io.BytesIO(
            st.load_blob_data(
                settings.blob_path("silver", *parts),
                stage=STAGE,
                container_name=settings.container,
            )
        )
    )


def main() -> None:
    s = load_settings(STAGE)
    ovc = overture_centroids(s)
    print(f"overture base: {len(ovc):,} unique buildings (reconciled against blob)\n")

    ms = _silver(s, "source=microsoft", f"adm0={ADM0}", "footprints.parquet")
    ms = ms[ms.damaged == 1].to_crs(M)

    ce = _silver(s, "source=copernicus_ems", f"adm0={ADM0}", "builtup_damage.parquet")
    ce = ce[(ce.layer_type == "point") & (ce.is_latest)].to_crs(M)

    raw = st.load_blob_data(
        s.blob_path("bronze", "source=unep_debris", f"adm0={ADM0}", "debris_buildings.gpkg"),
        stage=STAGE,
        container_name=s.container,
    )
    dtmp = os.path.join(tempfile.gettempdir(), "debris_buildings.gpkg")
    with open(dtmp, "wb") as f:
        f.write(raw)
    deb = pyogrio.read_dataframe(dtmp).to_crs(M)

    tree = cKDTree(ovc)
    print(f"native vs Overture-snapped ({SNAP_M} m) damaged-building counts:")
    for name, g in [
        ("Microsoft (footprints)", ms),
        ("CEMS (per-bldg points)", ce),
        ("UNEP debris (GBA polys)", deb),
    ]:
        c = g.geometry.centroid
        report(name, np.c_[c.x.values, c.y.values], tree, len(g))


if __name__ == "__main__":
    main()
