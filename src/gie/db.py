"""DuckDB connection helper — the shared data engine for ETL and serving.

A single DuckDB process is both the ETL engine (bronze -> silver -> gold) and
the read path for the viewer in v1. The ``spatial``, ``azure`` and ``h3``
extensions are loaded on every connection. Auth reuses the team's
``DSCI_AZ_BLOB_*`` SAS tokens (the same ones ocha-stratus uses) via a DuckDB
azure secret, so reads are cloud-optimized (column/row-group pruning, HTTP
range requests) instead of full-file downloads. See ``docs/decisions/0002``
(engine) and ``0003`` (Blob access) — including when this stops being enough
and we introduce PostGIS.
"""

from __future__ import annotations

import duckdb

from gie.config import Settings, load_settings


def connect(
    settings: Settings | None = None, *, write: bool = False
) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection with spatial/azure/h3 loaded and Azure auth set.

    ``spatial`` and ``azure`` are core extensions; ``h3`` is a community
    extension installed from the community repository. Pass ``write=True`` for
    ETL connections that upload to Blob (uses the write-scoped SAS token).
    """
    settings = settings or load_settings()
    con = duckdb.connect()

    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL azure; LOAD azure;")
    con.execute("INSTALL h3 FROM community; LOAD h3;")

    # SAS-token auth via a DuckDB azure secret. The token is read from the
    # environment in config; it is interpolated here (DuckDB does not bind
    # parameters in CREATE SECRET) and never logged.
    con.execute(
        f"""
        CREATE OR REPLACE SECRET azure_blob (
            TYPE azure,
            ACCOUNT_NAME '{settings.account_name}',
            CONNECTION_STRING '{settings.connection_string(write=write)}'
        );
        """
    )
    return con
