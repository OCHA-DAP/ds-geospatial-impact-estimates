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

# Which OSU delivery version the common model + serving tier publish. Both OSU
# silver versions are materialised side-by-side (silver/source=osu/.../version=<v>/)
# for cross-version analysis; downstream reads exactly ONE via this pointer (ADR-0009).
# Roll back by flipping to "v0" and rebuilding harmonize_common + build_platinum.
OSU_PUBLISHED_VERSION = "v1"

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
    # Data tier WITHIN the account (cheap prod/dev split, no separate account):
    # "dev" = the working copy the pipeline writes and staging reads; "prod" = the
    # promoted, published copy prod reads. Only the *served* tiers (gold, platinum)
    # are split, via a "-prod" dir suffix, so a gold/platinum refresh doesn't go
    # live until promote.py copies it across. Set GIE_TIER=prod ONLY on the prod
    # app slot (read side); pipelines + promote run without it (tier="dev") so they
    # always write the working copy.
    tier: Stage = "dev"

    def _served(self, base: str) -> str:
        """Tier-suffix a served-tier prefix (gold/platinum); dev = unchanged."""
        return f"{base}-prod" if self.tier == "prod" else base

    @property
    def platinum_prefix(self) -> str:
        """The platinum dir for this tier — 'platinum' (dev) or 'platinum-prod'."""
        return self._served("platinum")

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

    def blob_path(
        self, layer: Literal["bronze", "silver", "gold", "platinum"], *parts: str
    ) -> str:
        """Path within the container (no ``az://``/container) — for stratus writes.

        ``gold`` and ``platinum`` are tier-aware (``-prod`` suffix when
        ``tier=prod``); ``bronze``/``silver`` are the shared working copy.
        """
        prefix = {
            "bronze": self.bronze_prefix,
            "silver": self.silver_prefix,
            "gold": self._served(self.gold_prefix),
            "platinum": self.platinum_prefix,
        }[layer]
        return "/".join([self.project_prefix, prefix, *parts])

    def az_path(
        self, layer: Literal["bronze", "silver", "gold", "platinum"], *parts: str
    ) -> str:
        """Build an ``az://`` path the DuckDB azure extension understands."""
        return f"az://{self.container}/{self.blob_path(layer, *parts)}"


def load_settings(stage: Stage | None = None) -> Settings:
    """Resolve settings from the environment (``GIE_STAGE``/``GIE_CONTAINER``/...)."""
    resolved = stage or os.getenv("GIE_STAGE", "dev")
    if resolved not in ("dev", "prod"):
        raise ValueError(f"Invalid stage: {resolved!r} (expected 'dev' or 'prod')")
    tier = os.getenv("GIE_TIER", "dev")
    if tier not in ("dev", "prod"):
        raise ValueError(f"Invalid GIE_TIER: {tier!r} (expected 'dev' or 'prod')")
    return Settings(
        stage=resolved,  # type: ignore[arg-type]
        account_prefix=os.getenv("GIE_BLOB_ACCOUNT_PREFIX", ""),
        container=os.getenv("GIE_CONTAINER", "projects"),
        project_prefix=os.getenv("GIE_PROJECT_PREFIX", "ds-geospatial-impact-estimates"),
        tier=tier,  # type: ignore[arg-type]
    )
