"""Raster helpers: lossless COG conversion and a blob-or-local read resolver.

Two concerns live here:

* :func:`to_byte_cog` turns a categorical (small-integer) raster into a true,
  cloud-optimised GeoTIFF. It is *lossless by construction*: it refuses to write
  unless every pixel is a whole number within the target range, so a Float32
  class raster shrinks to a Byte COG with the pixel values bit-for-bit preserved
  (only the storage type and internal layout change, never the data). Overviews
  use ``mode`` resampling — the categorically-correct choice for class rasters
  (it picks a real class value, never an invented average).

* :func:`open_local_or_blob` resolves a bronze raster to something rasterio can
  open, preferring a local mirror when present and otherwise pulling the blob to
  a temp file (mirrors ``harmonize_impact_sar``). This is what lets downstream
  code "work from blob or local" without caring which.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager

import numpy as np
import rasterio
import rasterio.shutil as rio_shutil
from pyproj import Transformer
from rasterio.transform import rowcol
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from shapely.geometry import box

# Read/convert in horizontal strips so a multi-GB source never lands in RAM at
# once (a 4096-row strip of a ~33k-wide band is ~0.5 GB float32).
_STRIP_ROWS = 4096


def to_byte_cog(src: str, dst: str, *, max_value: int = 255, strip_rows: int = _STRIP_ROWS) -> dict[int, int]:
    """Write ``src`` to ``dst`` as a lossless Byte DEFLATE COG.

    Raises ``ValueError`` if any pixel is not a whole number in ``[0, max_value]``
    — i.e. it will not proceed if the Byte cast would alter a single value. This
    is the guard that makes "compress but don't change the data" enforceable
    rather than a hope. Returns a ``{value: pixel_count}`` histogram.
    """
    counts: dict[int, int] = {}
    # Stage a plain tiled GTiff first, then let the COG driver finalise it (build
    # overviews + reorder IFDs) — the driver is a copy driver and won't accept
    # random-window writes directly.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tif", dir=os.path.dirname(dst) or None)
    os.close(tmp_fd)
    try:
        with rasterio.open(src) as s:
            profile = s.profile.copy()
            profile.update(
                driver="GTiff", dtype="uint8", nodata=None, tiled=True,
                blockxsize=512, blockysize=512, compress="deflate",
                predictor=2, BIGTIFF="IF_SAFER",
            )
            with rasterio.open(tmp_path, "w", **profile) as t:
                for row in range(0, s.height, strip_rows):
                    h = min(strip_rows, s.height - row)
                    win = Window(0, row, s.width, h)
                    a = s.read(1, window=win)
                    if not (np.array_equal(a, np.rint(a)) and a.min() >= 0 and a.max() <= max_value):
                        raise ValueError(
                            f"{src}: values are not whole numbers in [0, {max_value}] "
                            "— refusing a lossy Byte cast (data would change)."
                        )
                    u, c = np.unique(a, return_counts=True)
                    for k, v in zip(u.tolist(), c.tolist()):
                        counts[int(k)] = counts.get(int(k), 0) + int(v)
                    t.write(a.astype("uint8"), 1, window=win)
        rio_shutil.copy(
            tmp_path, dst, driver="COG", compress="DEFLATE", predictor=2,
            overview_resampling="mode", blocksize=512,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return counts


def raster_lonlat_bounds(path: str) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a raster's extent in EPSG:4326.

    Metadata-only (no pixel read) — use it to pre-filter which building centroids
    to sample, whatever the raster's own CRS.
    """
    with rasterio.open(path) as s:
        return transform_bounds(s.crs, 4326, *s.bounds)


def sample_points(path: str, lon, lat, *, fill: int = 0) -> np.ndarray:
    """Band-1 pixel value at each (lon, lat) given in EPSG:4326.

    Reprojects the points into the raster's CRS, so it works regardless of that
    CRS (LIST is UTM 18N; the SAR proxy is 4326). Points outside the extent get
    ``fill``. Reads the full band once (fast random access; a categorical Byte
    raster is small in memory).
    """
    lon, lat = np.asarray(lon), np.asarray(lat)
    with rasterio.open(path) as s:
        arr = s.read(1)
        transform, (h, w), crs = s.transform, s.shape, s.crs
    x, y = Transformer.from_crs(4326, crs, always_xy=True).transform(lon, lat)
    rows, cols = np.asarray(rowcol(transform, x, y))
    inb = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    out = np.full(lon.shape, fill, dtype=arr.dtype)
    out[inb] = arr[rows[inb], cols[inb]]
    return out


def raster_footprint(path: str, *, segmentize_m: float = 10_000):
    """The raster's rectangular extent as a shapely polygon in EPSG:4326.

    The rectangle is densified (``segmentize_m``) before reprojection so its
    edges follow the true curved boundary rather than straight endpoint-to-
    endpoint lines over a long span.
    """
    import geopandas as gpd

    with rasterio.open(path) as s:
        rect = box(*s.bounds).segmentize(segmentize_m)
        crs = s.crs
    return gpd.GeoSeries([rect], crs=crs).to_crs(4326).iloc[0]


@contextmanager
def open_local_or_blob(settings, blob_path: str, *, local_dir: str | None = None):
    """Yield a filesystem path to a bronze raster, preferring a local mirror.

    If ``local_dir`` (or ``$GIE_LIST_LOCAL_DIR``) holds a file named like the
    blob's basename, that path is yielded as-is and left in place. Otherwise the
    blob is fetched to a temp file that is deleted on exit. Lets downstream code
    read the same raster from blob or a local copy interchangeably — useful when
    a source is too large to round-trip through blob comfortably::

        with open_local_or_blob(settings, bpath) as path:
            with rasterio.open(path) as src:
                ...
    """
    name = blob_path.rsplit("/", 1)[-1]
    local_dir = local_dir or os.getenv("GIE_LIST_LOCAL_DIR")
    if local_dir:
        candidate = os.path.join(os.path.expanduser(local_dir), name)
        if os.path.isfile(candidate):
            yield candidate
            return

    import ocha_stratus as stratus

    data = stratus.load_blob_data(
        blob_path, stage=settings.stage, container_name=settings.container
    )
    fd, tmp = tempfile.mkstemp(suffix="_" + name)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    try:
        yield tmp
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
