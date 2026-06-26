"""Configuration for the geospatial impact estimates project.

Settings come from environment variables (loaded from a local ``.env`` in
development). The data lake lives in Azure Blob Storage under a medallion
layout; see ``docs/decisions/0002`` for the storage and engine rationale.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Default H3 resolution for the harmonization grid. Res 8 ~= 0.74 km2 cells,
# a reasonable city-scale default for an earthquake response; revisit per event.
DEFAULT_H3_RESOLUTION = 8


@dataclass(frozen=True)
class Settings:
    """Azure Blob + medallion layout settings, resolved from the environment."""

    storage_account: str
    container: str
    # Medallion prefixes within the container (see docs/decisions/0002).
    bronze_prefix: str = "bronze"
    silver_prefix: str = "silver"
    gold_prefix: str = "gold"

    @property
    def account_url(self) -> str:
        return f"https://{self.storage_account}.blob.core.windows.net"

    def abfss(self, layer: str, *parts: str) -> str:
        """Build an ``az://`` path the DuckDB azure extension understands."""
        prefix = {
            "bronze": self.bronze_prefix,
            "silver": self.silver_prefix,
            "gold": self.gold_prefix,
        }[layer]
        path = "/".join([prefix, *parts])
        return f"az://{self.container}/{path}"


def load_settings() -> Settings:
    """Load settings from the environment.

    Required: ``GIE_STORAGE_ACCOUNT``, ``GIE_CONTAINER``.
    """
    try:
        return Settings(
            storage_account=os.environ["GIE_STORAGE_ACCOUNT"],
            container=os.environ["GIE_CONTAINER"],
        )
    except KeyError as exc:
        raise RuntimeError(
            f"Missing required environment variable: {exc.args[0]}. "
            "Copy .env.example to .env and fill it in."
        ) from exc
