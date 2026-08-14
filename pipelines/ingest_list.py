"""One-time loader: LIST ResNet pre/post change-detection damage rasters -> bronze.

LIST delivered two 10 m raster damage classifications for the 2026 Venezuela
earthquake, produced by a ResNet run over paired pre- and post-event imagery
("predicted_resnet_prepost..."). They arrive as two adjacent scene footprints
covering the central coast (incl. La Guaira): a western scene (~70.7-67.8 W,
"scene2") and an eastern scene (~68.7-65.7 W). Both are EPSG:32618 (UTM 18N,
used well outside its nominal zone but internally consistent), single band.

Class values are integers {0, 1, 2}: 0 dominates (~99.4 %), with sparse 1 and 2.
The provider's exact semantics for 1 vs 2 (e.g. damage grade) are not yet
confirmed — treat as a preliminary change-detection damage proxy, NOT confirmed
building damage, until documented (mirror the caveat discipline of the SAR
proxy).

As delivered each scene is a ~5.3 GB striped Float32 GeoTIFF (values still just
{0,1,2}) — needlessly large and not cloud-optimised. This loader lands each as a
*lossless* Byte DEFLATE COG (~7 MB): the pixel values are preserved bit-for-bit
(:func:`gie.raster.to_byte_cog` refuses to write if any value isn't a whole
number in range), only the storage type and layout change. That makes the bronze
copy a true COG the pipeline can stream straight from blob. The source is read
in place from the delivery zip via ``/vsizip`` — no multi-GB extraction.

Run: uv run --group etl python pipelines/ingest_list.py [path-to-LIST.zip]
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile

from gie import blobio, events, ledger
from gie.config import load_settings
from gie.raster import to_byte_cog

SOURCE = "list"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
DEFAULT_SRC = os.path.expanduser("~/Downloads/LIST.zip")


def _tif_members(src: str) -> list[tuple[str, str]]:
    """(gdal_path, basename) for each .tif to ingest, from a zip / dir / .tif."""
    if src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".tif")]
        return [(f"/vsizip/{{{src}}}/{n}", os.path.basename(n)) for n in sorted(names)]
    if os.path.isdir(src):
        tifs = [f for f in sorted(os.listdir(src)) if f.lower().endswith(".tif")]
        return [(os.path.join(src, f), f) for f in tifs]
    return [(src, os.path.basename(src))]


def main() -> None:
    events.require_event(EVENT)
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.exists(src):
        raise SystemExit(f"source not found: {src}")

    members = _tif_members(src)
    if not members:
        raise SystemExit(f"no .tif found in {src}")

    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)

    for gdal_path, name in members:
        with tempfile.TemporaryDirectory() as tmp:
            cog = os.path.join(tmp, name)
            print(f"converting {name} -> lossless Byte COG ...", flush=True)
            counts = to_byte_cog(gdal_path, cog)
            size = os.path.getsize(cog)
            blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name, event=EVENT)
            print(f"uploading {name} ({size / 1e6:.1f} MB) -> {blob}", flush=True)
            with open(cog, "rb") as f:
                blobio.upload(fs, f.read(), blob)

        ledger.record(
            SOURCE,
            "bronze",
            f"LIST ResNet pre/post change-detection damage classes ({name})",
            blob,
            "10 m Byte COG, EPSG:32618, class values {0,1,2} (0~99.4%); lossless "
            "conversion of delivered ~5.3 GB Float32 GeoTIFF (values unchanged); "
            f"pixel counts {counts}; preliminary change-detection proxy, 1-vs-2 "
            "semantics unconfirmed (see module docstring)",
            status="ingesting",
        )
        print(f"bronze <- {blob}  counts={counts}", flush=True)


if __name__ == "__main__":
    main()
