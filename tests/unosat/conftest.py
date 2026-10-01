import io
import zipfile

import pandas as pd
import pytest

from gie.unosat import common


def make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def good_zip() -> bytes:
    return make_zip(
        {
            "FL20220424SSD_SHP/VIIRS_20241214_20241218_FloodExtent_SouthSudan.shp": b"shp",
            "FL20220424SSD_SHP/VIIRS_20241214_20241218_FloodExtent_SouthSudan.dbf": b"dbf",
        }
    )


@pytest.fixture
def ledger_row() -> pd.Series:
    row = {c: None for c in common.LEDGER_COLS}
    row.update(
        target_id="r-shp@2024-12-20T09:00:00", resource_id="r-shp",
        resource_name="FL20220424SSD_SHP.zip", format="SHP",
        url="https://unosat.org/static/x/FL20220424SSD_SHP.zip", host="unosat.org",
        event_code="FL20220424SSD", hazard_prefix="FL", iso3="SSD", scope="flood",
        licence="cc-by-sa", status="pending", attempts=0, missing_upstream=False,
    )
    return pd.Series(row)


class FakeResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Length": str(len(body))}

    def iter_content(self, chunk_size: int):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    """Maps url -> FakeResponse or an Exception instance to raise."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, *, stream=True, timeout=None):
        self.calls.append(url)
        r = self.routes[url]
        if isinstance(r, Exception):
            raise r
        return r
