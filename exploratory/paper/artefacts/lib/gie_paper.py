"""Archived scripts import `gie_paper` from here; the library lives in exploratory/paper/lib.
This module replaces itself in sys.modules with the real one, so `import gie_paper as gp`
anywhere in the archive yields exploratory/paper/lib/gie_paper.py (same conventions, same switches)."""
import importlib.util
import os
import sys

_REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "gie_paper.py")
_spec = importlib.util.spec_from_file_location("gie_paper", _REAL)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[__name__] = _mod          # before exec: the real module may import itself by name
_spec.loader.exec_module(_mod)
