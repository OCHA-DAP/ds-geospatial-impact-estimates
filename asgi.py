"""Production ASGI entry point for Azure App Service.

Gunicorn runs ``asgi:app`` from the deployed root. We add ``src/`` to the path so
the ``gie`` package imports without being pip-installed, then expose the FastAPI
app (which also serves the built SPA from ``web/dist``). Locally, keep using
``uvicorn api.main:app`` — this file is only needed for the deployed server.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from api.main import app  # noqa: E402  (path set up above)

__all__ = ["app"]
