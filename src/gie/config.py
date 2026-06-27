"""Configuration for the geospatial impact estimates project.

Settings come from environment variables (loaded from a local ``.env`` in
development). The data lake lives in the team Azure Blob account under a
medallion layout; we reuse the same ``DSCI_AZ_BLOB_*`` SAS tokens as
``ocha-stratus`` but query through DuckDB directly (see
``docs/decisions/0002`` and ``0003``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# Default H3 resolution for the harmonization grid. Res 8 ~= 0.74 km2 cells,
# a reasonable city-scale default for an earthquake response; revisit per event.
DEFAULT_H3_RESOLUTION = 8

Stage = Literal["dev", "prod"]


@dataclass(frozen=True)
class Settings:
    """Azure Blob + medallion layout settings.

    Storage account is ``{account_prefix}{stage}`` — set ``account_prefix`` via
    ``GIE_BLOB_ACCOUNT_PREFIX`` (kept out of the repo). Paths live under
    ``{container}/{project_prefix}/{layer}/...``.
    """

    stage: Stage = "dev"
    account_prefix: str = ""
    container: str = "projects"
    project_prefix: str = "ds-geospatial-impact-estimates"
    bronze_prefix: str = "bronze"
    silver_prefix: str = "silver"
    gold_prefix: str = "gold"

    @property
    def account_name(self) -> str:
        if not self.account_prefix:
            raise RuntimeError(
                "Storage account prefix not set — define GIE_BLOB_ACCOUNT_PREFIX "
                "in your .env (the team blob-account prefix)."
            )
        return f"{self.account_prefix}{self.stage}"

    @property
    def account_host(self) -> str:
        return f"{self.account_name}.blob.core.windows.net"

    def sas_token(self, *, write: bool = False) -> str:
        """Read the team SAS token from the environment (shared with ocha-stratus).

        ``write`` requires the write-scoped token; reads accept either token.
        Tokens are secrets and are only ever read from the environment, never
        stored in code or committed config.
        """
        suffix = self.stage.upper()
        keys = (
            [f"DSCI_AZ_BLOB_{suffix}_SAS_WRITE"]
            if write
            else [f"DSCI_AZ_BLOB_{suffix}_SAS", f"DSCI_AZ_BLOB_{suffix}_SAS_WRITE"]
        )
        for key in keys:
            token = os.getenv(key)
            if token:
                return token.lstrip("?")
        raise RuntimeError(
            f"No SAS token found. Set one of {keys} in your .env "
            "(same tokens used by ocha-stratus)."
        )

    def connection_string(self, *, write: bool = False) -> str:
        """Azure connection string embedding the SAS token, for a DuckDB secret."""
        return (
            f"BlobEndpoint=https://{self.account_host};"
            f"SharedAccessSignature={self.sas_token(write=write)}"
        )

    def blob_path(self, layer: Literal["bronze", "silver", "gold"], *parts: str) -> str:
        """Path within the container (no ``az://``/container) — for stratus writes."""
        prefix = {
            "bronze": self.bronze_prefix,
            "silver": self.silver_prefix,
            "gold": self.gold_prefix,
        }[layer]
        return "/".join([self.project_prefix, prefix, *parts])

    def az_path(self, layer: Literal["bronze", "silver", "gold"], *parts: str) -> str:
        """Build an ``az://`` path the DuckDB azure extension understands."""
        return f"az://{self.container}/{self.blob_path(layer, *parts)}"


def load_settings(stage: Stage | None = None) -> Settings:
    """Resolve settings from the environment (``GIE_STAGE``/``GIE_CONTAINER``/...)."""
    resolved = stage or os.getenv("GIE_STAGE", "dev")
    if resolved not in ("dev", "prod"):
        raise ValueError(f"Invalid stage: {resolved!r} (expected 'dev' or 'prod')")
    return Settings(
        stage=resolved,  # type: ignore[arg-type]
        account_prefix=os.getenv("GIE_BLOB_ACCOUNT_PREFIX", ""),
        container=os.getenv("GIE_CONTAINER", "projects"),
        project_prefix=os.getenv("GIE_PROJECT_PREFIX", "ds-geospatial-impact-estimates"),
    )
