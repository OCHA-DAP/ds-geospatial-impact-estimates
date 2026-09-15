"""Archived scripts import from here; the library now lives in exploratory/paper/lib."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from gie_paper import *  # noqa: F401,F403
from gie_paper import _read_pq, _read_gpkg  # noqa: F401
