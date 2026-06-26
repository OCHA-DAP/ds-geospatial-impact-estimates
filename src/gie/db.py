"""DuckDB connection helper — the shared data engine for ETL and serving.

A single DuckDB process is both the ETL engine (bronze -> silver -> gold) and
the read path for the viewer in v1. The ``spatial``, ``azure`` and ``h3``
extensions are loaded on every connection; Azure auth uses the credential
chain (managed identity in Azure, az-cli / env locally) so no secrets are
embedded. See ``docs/decisions/0002`` for when this stops being enough and we
introduce PostGIS.
"""

from __future__ import annotations

import duckdb

from gie.config import Settings, load_settings


def connect(settings: Settings | None = None) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection with spatial/azure/h3 loaded and Azure auth set.

    ``spatial`` and ``azure`` are core extensions; ``h3`` is a community
    extension and must be installed from the community repository.
    """
    settings = settings or load_settings()
    con = duckdb.connect()

    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL azure; LOAD azure;")
    con.execute("INSTALL h3 FROM community; LOAD h3;")

    # Credential-chain auth resolves managed identity in Azure and falls back to
    # the Azure CLI / environment locally — no keys in code or config.
    con.execute(
        """
        CREATE OR REPLACE SECRET azure_blob (
            TYPE azure,
            PROVIDER credential_chain,
            ACCOUNT_NAME $account
        );
        """,
        {"account": settings.storage_account},
    )
    return con
